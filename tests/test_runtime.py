import socket
from typing import cast

import httpx
import pytest
from fastapi import APIRouter

from app.providers.lifespan_provider import Resources
from app.services.auth.local_auth_service import LocalResources
from app.services.auth.modules import AuthModule, AuthModuleFactory
from bootstrap.application import create_app
from config.settings import Settings
from tests.conftest import AppFactory, EmailRecorder, SmsRecorder, make_settings


def test_factory_defaults_to_no_auth_and_validates_module_selection() -> None:
    app = create_app(make_settings(APP_API_PREFIX='/v2', APP_DEBUG=True))
    assert app.state.resources is None and app.state.jwt_settings is None
    schema = app.openapi()
    assert '/v2/ping' in schema['paths'] and '/v2/auth/register' not in schema['paths']
    assert not schema.get('components', {}).get('securitySchemes')
    assert app.state.resources is None

    # 无认证合法，误拼或重复选择不能静默降级成无认证
    for selection in (['unknown'], ['password', 'password'], ['']):
        with pytest.raises(ValueError, match='AUTH_MODULES'):
            create_app(make_settings(AUTH_MODULES=selection))
    with pytest.raises(ValueError, match='local token settings'):
        create_app(make_settings(AUTH_MODULES=['password']))

    # 自定义入口必须遵守唯一的method/path契约
    def duplicate(settings: Settings) -> AuthModule:
        router = APIRouter()

        @router.get('/same')
        async def first() -> bool:
            return True

        @router.get('/same')
        async def second() -> bool:
            return True

        return AuthModule('custom', router)

    with pytest.raises(ValueError, match='Duplicate route'):
        create_app(
            make_settings(AUTH_MODULES=['custom']), auth_module_factories=[AuthModuleFactory('custom', duplicate)]
        )


async def test_lifespan_only_owns_selected_senders_and_closes_each_cycle() -> None:
    settings = make_settings(
        AUTH_MODULES=['phone_otp', 'email_otp'],
        JWT_SECRET_KEY='test-jwt-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        AUTH_CODE_SECRET_KEY='test-code-key-yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy',
    )
    invalid = create_app(settings)
    with pytest.raises(RuntimeError, match='sms_sender_factory'):
        async with invalid.router.lifespan_context(invalid):
            pytest.fail('Selected phone module requires a sender')
    assert invalid.state.resources is None

    # 两个应用同时存活，结束一个不能关闭另一个的资源
    first = create_app(settings, sms_sender_factory=SmsRecorder, email_sender_factory=EmailRecorder)
    second = create_app(settings, sms_sender_factory=SmsRecorder, email_sender_factory=EmailRecorder)
    async with first.router.lifespan_context(first):
        resource = cast(Resources, first.state.resources)
        local = cast(LocalResources, first.state.local_auth_resources)
        assert isinstance(local.sms_sender, SmsRecorder) and isinstance(local.email_sender, EmailRecorder)
        async with second.router.lifespan_context(second):
            other = cast(Resources, second.state.resources)
            other_local = cast(LocalResources, second.state.local_auth_resources)
            assert isinstance(other_local.sms_sender, SmsRecorder) and isinstance(
                other_local.email_sender, EmailRecorder
            )
            assert resource.engine is not other.engine and resource.redis_pool is not other.redis_pool
        assert other_local.sms_sender.closed and other_local.email_sender.closed
        assert not local.sms_sender.closed and not local.email_sender.closed
        assert other.httpx_client.is_closed and not resource.httpx_client.is_closed
    assert local.sms_sender.closed and local.email_sender.closed and resource.httpx_client.is_closed

    # 重复lifespan必须得到新实例，不能复活已经关闭的发送器
    async with first.router.lifespan_context(first):
        repeated = cast(Resources, first.state.resources)
        repeated_local = cast(LocalResources, first.state.local_auth_resources)
        assert repeated.engine is not resource.engine and not repeated.httpx_client.is_closed
        assert isinstance(repeated_local.sms_sender, SmsRecorder) and not repeated_local.sms_sender.closed
        assert isinstance(repeated_local.email_sender, EmailRecorder) and not repeated_local.email_sender.closed
    assert repeated_local.sms_sender.closed and repeated_local.email_sender.closed
    assert first.state.resources is None and first.state.local_auth_resources is None


@pytest.mark.integration
async def test_no_auth_public_api_and_dependency_outage(
    app_factory: AppFactory, integration_settings: Settings
) -> None:
    application = await app_factory(JWT_SECRET_KEY=None, AUTH_CODE_SECRET_KEY=None)
    client = application.client
    assert application.app.state.jwt_settings is None and application.sms is None and application.email is None
    assert (await client.get('/api/ping')).json() == 'pong'
    assert (await client.get('/api/health/ready')).status_code == 200
    for path, method in (
        ('/api/auth/register', 'POST'),
        ('/api/auth/password/token', 'POST'),
        ('/api/auth/phone/token', 'POST'),
        ('/api/auth/email/token', 'POST'),
        ('/api/auth/token/status', 'GET'),
        ('/api/users/me', 'GET'),
    ):
        assert (await client.request(method, path)).status_code == 404
    assert not application.app.openapi().get('components', {}).get('securitySchemes')

    # 保留一个不监听的端口，让真实Redis连接失败而不模拟其算法
    with socket.socket() as unavailable:
        unavailable.bind(('127.0.0.1', 0))
        settings = make_settings(**{
            **integration_settings.model_dump(),
            'AUTH_MODULES': ['password'],
            'JWT_SECRET_KEY': 'test-jwt-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
            'REDIS_HOST': '127.0.0.1',
            'REDIS_PORT': unavailable.getsockname()[1],
        })
        broken = create_app(settings)
        async with broken.router.lifespan_context(broken):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=broken), base_url='http://test') as failed:
                assert (await failed.get('/api/users/me')).status_code == 503
                assert (await failed.get('/api/ping')).json() == 'pong'
                assert (await failed.get('/api/health/live')).status_code == 200
                ready = await failed.get('/api/health/ready')
                assert ready.status_code == 503
                assert ready.json() == {'status': 'not_ready', 'database': 'ok', 'redis': 'unavailable'}
