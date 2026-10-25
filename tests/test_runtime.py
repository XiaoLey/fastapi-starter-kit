import socket
from typing import cast

import httpx
import pytest

from app.providers.lifespan_provider import Resources
from bootstrap.application import create_app
from config.settings import Settings
from tests.conftest import SmsRecorder, make_settings


def test_factory_and_openapi_do_not_start_resources() -> None:
    app = create_app(make_settings(APP_API_PREFIX='/v2', APP_DEBUG=True))
    assert app.state.resources is None
    assert app.openapi()['paths']['/v2/users']['post']['responses']['201']
    assert app.state.resources is None


async def test_lifespan_owns_resources_and_requires_sms_factory() -> None:
    settings = make_settings(SMS_ENABLED=True)
    invalid = create_app(settings)
    with pytest.raises(RuntimeError, match='sms_sender_factory'):
        async with invalid.router.lifespan_context(invalid):
            pytest.fail('SMS must not start without a sender')

    # 两个应用共存时，关闭一个不能关闭另一个的资源
    first = create_app(settings, sms_sender_factory=SmsRecorder)
    second = create_app(settings, sms_sender_factory=SmsRecorder)
    async with first.router.lifespan_context(first):
        resource = cast(Resources, first.state.resources)
        assert isinstance(resource.sms_sender, SmsRecorder)
        async with second.router.lifespan_context(second):
            other = cast(Resources, second.state.resources)
            assert isinstance(other.sms_sender, SmsRecorder)
            assert resource.engine is not other.engine and resource.redis_pool is not other.redis_pool
        assert other.sms_sender.closed and not resource.sms_sender.closed
        assert other.httpx_client.is_closed and not resource.httpx_client.is_closed
    assert resource.sms_sender.closed and resource.httpx_client.is_closed

    # 同一工厂重复运行时必须获得新的可用资源
    async with first.router.lifespan_context(first):
        repeated = cast(Resources, first.state.resources)
        assert repeated.engine is not resource.engine and not repeated.httpx_client.is_closed
        assert isinstance(repeated.sms_sender, SmsRecorder) and not repeated.sms_sender.closed
    assert repeated.sms_sender.closed and repeated.httpx_client.is_closed
    assert first.state.resources is None and second.state.resources is None


@pytest.mark.integration
async def test_sms_disabled_and_dependency_outage(integration_settings: Settings) -> None:
    settings = integration_settings.model_copy(update={'SMS_ENABLED': False})
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            # 默认短信不可用，不妨碍普通用户名注册
            response = await client.post(
                '/api/auth/verification-codes/cellphone', json={'cellphone': '13800000000', 'purpose': 'login'}
            )
            assert response.status_code == 503 and response.json()['code'] == 'SMS_UNAVAILABLE'
            assert (
                await client.post(
                    '/api/users',
                    json={
                        'username': 'no-sms',
                        'password': 'long-password-123',
                        'nickname': '普通账号',
                        'gender': 'unknown',
                    },
                )
            ).status_code == 201

    # 保留一个不监听的本地端口，真实连接失败而非模拟Redis算法
    with socket.socket() as unavailable:
        unavailable.bind(('127.0.0.1', 0))
        broken = create_app(
            settings.model_copy(update={'REDIS_HOST': '127.0.0.1', 'REDIS_PORT': unavailable.getsockname()[1]})
        )
        async with broken.router.lifespan_context(broken):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=broken), base_url='http://test') as client:
                assert (await client.get('/api/users/me')).status_code == 503
                assert (await client.get('/api/ping')).json() == 'pong'
                assert (await client.get('/api/health/live')).status_code == 200
                ready = await client.get('/api/health/ready')
                assert ready.status_code == 503
                assert ready.json() == {'status': 'not_ready', 'database': 'ok', 'redis': 'unavailable'}
