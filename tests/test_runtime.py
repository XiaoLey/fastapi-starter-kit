import asyncio
import logging
import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Literal, cast

import httpx
import pytest
from fastapi import APIRouter, FastAPI, WebSocket
from pydantic import field_validator
from starlette.types import Message

from app.exceptions import SafeValueError
from app.http import api
from app.http.auth_methods.registration import RegistrationSc
from app.providers.lifespan_provider import Resources
from app.schemas.base import BaseSc
from app.services.auth.local_auth_service import LocalResources
from app.services.auth.modules import AuthModule
from bootstrap.application import create_app
from config.settings import Settings, load_settings
from tests.conftest import SENSITIVE_TEST_VALUE, AppFactory, EmailRecorder, SmsRecorder, make_settings


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

    # 嵌套路由也必须遵守唯一的 method/path 契约
    def duplicate(settings: Settings) -> AuthModule:
        nested = APIRouter(prefix='/nested')

        @nested.get('/same')
        async def first() -> bool:
            return True

        @nested.get('/same')
        async def second() -> bool:
            return True

        router = APIRouter()
        router.include_router(nested)
        return AuthModule(router=router)

    with pytest.raises(ValueError, match='Duplicate route'):
        create_app(make_settings(AUTH_MODULES=['custom']), auth_module_factories={'custom': duplicate})


async def test_explicit_business_routes_keep_health_independent(monkeypatch: pytest.MonkeyPatch) -> None:
    router = APIRouter(prefix='/business')

    @router.get('/status')
    async def business_status() -> bool:
        return True

    @router.websocket('/events')
    async def business_events(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    # 同一个标准 router 同时接纳 HTTP/WS，不依赖文件名或特殊属性名
    monkeypatch.setattr(api, 'router', router)
    app = create_app(make_settings(APP_API_PREFIX='/v2'), auth_module_factories={})
    assert str(app.url_path_for('business_status')) == '/v2/business/status'
    assert str(app.url_path_for('business_events')) == '/v2/business/events'
    assert '/v2/business/status' in app.openapi()['paths']
    assert '/v2/auth/register' not in app.openapi()['paths']

    # 不创建任何运行资源也能调用存活探针
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get('/v2/ping')).json() == 'pong'
        assert (await client.get('/v2/health/live')).json() == {'status': 'alive'}
    assert app.state.resources is None


async def test_lifespan_only_owns_selected_senders_and_closes_each_cycle(log_messages: list[str]) -> None:
    settings = make_settings(
        AUTH_MODULES=['password', 'phone_otp', 'email_otp'],
        JWT_SECRET_KEY='test-jwt-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        AUTH_CODE_SECRET_KEY='test-code-key-yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy',
    )
    invalid = create_app(settings)
    with pytest.raises(SafeValueError, match='sms_sender_factory'):
        async with invalid.router.lifespan_context(invalid):
            pytest.fail('Selected phone module requires a sender')
    assert invalid.state.resources is None

    # 三个内置模块在每个应用的每轮启动中共享一次发送器创建
    created_sms: list[SmsRecorder] = []
    created_email: list[EmailRecorder] = []

    def sms_factory() -> SmsRecorder:
        sender = SmsRecorder()
        created_sms.append(sender)
        return sender

    def email_factory() -> EmailRecorder:
        sender = EmailRecorder()
        created_email.append(sender)
        return sender

    # 两个应用同时存活，结束一个不能关闭另一个的资源
    first = create_app(settings, sms_sender_factory=sms_factory, email_sender_factory=email_factory)
    second = create_app(settings, sms_sender_factory=sms_factory, email_sender_factory=email_factory)
    async with first.router.lifespan_context(first):
        resource = cast(Resources, first.state.resources)
        local = cast(LocalResources, first.state.local_auth_resources)
        assert isinstance(local.sms_sender, SmsRecorder) and isinstance(local.email_sender, EmailRecorder)
        assert len(created_sms) == len(created_email) == 1
        async with second.router.lifespan_context(second):
            other = cast(Resources, second.state.resources)
            other_local = cast(LocalResources, second.state.local_auth_resources)
            assert isinstance(other_local.sms_sender, SmsRecorder) and isinstance(
                other_local.email_sender, EmailRecorder
            )
            assert resource.engine is not other.engine and resource.redis_pool is not other.redis_pool
            assert len(created_sms) == len(created_email) == 2
        assert other_local.sms_sender.closed and other_local.email_sender.closed
        assert not local.sms_sender.closed and not local.email_sender.closed
        assert other.httpx_client.is_closed and not resource.httpx_client.is_closed
    assert local.sms_sender.closed and local.email_sender.closed and resource.httpx_client.is_closed

    # 重复 lifespan 必须得到新实例，不能复活已经关闭的发送器
    async with first.router.lifespan_context(first):
        repeated = cast(Resources, first.state.resources)
        repeated_local = cast(LocalResources, first.state.local_auth_resources)
        assert repeated.engine is not resource.engine and not repeated.httpx_client.is_closed
        assert isinstance(repeated_local.sms_sender, SmsRecorder) and not repeated_local.sms_sender.closed
        assert isinstance(repeated_local.email_sender, EmailRecorder) and not repeated_local.email_sender.closed
        assert len(created_sms) == len(created_email) == 3
    assert repeated_local.sms_sender.closed and repeated_local.email_sender.closed
    assert first.state.resources is None and first.state.local_auth_resources is None

    # 后创建的发送器失败时，已创建的发送器仍要关闭且原始供应商文本不能外泄
    def failed_email() -> EmailRecorder:
        raise RuntimeError(SENSITIVE_TEST_VALUE)

    broken = create_app(settings, sms_sender_factory=sms_factory, email_sender_factory=failed_email)
    with pytest.raises(SafeValueError, match='Email sender initialization failed') as failure:
        async with broken.router.lifespan_context(broken):
            pytest.fail('Sender initialization must fail')
    assert created_sms[-1].closed and broken.state.resources is None
    assert SENSITIVE_TEST_VALUE not in str(failure.value) + ''.join(log_messages)


def test_configuration_reports_safe_reasons(monkeypatch: pytest.MonkeyPatch) -> None:
    # 配置错误必须来自隔离输入，不能读取真实 dotenv
    monkeypatch.setitem(Settings.model_config, 'env_file', None)
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('APP_DEBUG', 'true')
    monkeypatch.setenv('REDIS_KEY_PREFIX', 'test-config')
    monkeypatch.setenv('POSTGRES_PASSWORD', SENSITIVE_TEST_VALUE)
    monkeypatch.setenv('REDIS_PASSWORD', SENSITIVE_TEST_VALUE)
    with pytest.raises(SafeValueError, match='APP_DEBUG=false') as debug_failure:
        load_settings()
    assert SENSITIVE_TEST_VALUE not in str(debug_failure.value)

    # 模型级约束必须指出可修改的配置项，而不是只剩一个 value_error
    monkeypatch.setenv('APP_DEBUG', 'false')
    monkeypatch.setenv('REDIS_KEY_PREFIX', 'fastapi')
    with pytest.raises(SafeValueError, match='REDIS_KEY_PREFIX'):
        load_settings()

    # 普通解析失败仍只显示位置和类型，不回显未通过解析的输入
    monkeypatch.setenv('POSTGRES_PORT', SENSITIVE_TEST_VALUE)
    with pytest.raises(SafeValueError, match='POSTGRES_PORT') as parse_failure:
        load_settings()
    assert 'int_parsing' in str(parse_failure.value)
    assert SENSITIVE_TEST_VALUE not in str(parse_failure.value)


async def test_safe_validation_and_http_errors(log_messages: list[str], caplog: pytest.LogCaptureFixture) -> None:
    class UntrustedInput(BaseSc):
        value: str

        @field_validator('value')
        @classmethod
        def reject(cls, value: str) -> str:
            raise ValueError(f'{SENSITIVE_TEST_VALUE}: {value}')

    app = create_app(make_settings(APP_DEBUG=True, APP_CORS_ORIGINS=['https://browser.example']))

    # 直接使用公开路由接口组合错误边界，不替换 Redis 或数据库算法
    @app.post('/_registration')
    async def registration(data: RegistrationSc) -> bool:
        return True

    @app.post('/_untrusted')
    async def untrusted(data: UntrustedInput) -> bool:
        return True

    @app.get('/_internal', response_model=UntrustedInput)
    async def internal() -> dict[str, str]:
        return {'value': SENSITIVE_TEST_VALUE}

    @app.get('/_failure')
    async def failure() -> None:
        raise RuntimeError(SENSITIVE_TEST_VALUE)

    with caplog.at_level(logging.INFO):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url='http://test',
            headers={'Origin': 'https://browser.example'},
        ) as client:
            # 同样的模型级 422 能明确区分缺密码与重复身份
            identity = {'kind': 'username', 'identifier': 'tester'}
            missing = await client.post('/_registration', json={'identities': [identity]})
            duplicate = await client.post(
                '/_registration', json={'identities': [identity, identity], 'password': SENSITIVE_TEST_VALUE}
            )
            assert missing.status_code == duplicate.status_code == 422
            assert missing.json()['detail'][0]['message'] == 'Username registration requires a password'
            assert duplicate.json()['detail'][0]['message'] == 'Each local identity kind may occur only once'
            assert SENSITIVE_TEST_VALUE not in duplicate.text

            # 普通 validator 的 msg/ctx 和 URL 查询参数都不是安全日志输入
            unknown = await client.post(
                f'/_untrusted?secret={SENSITIVE_TEST_VALUE}', json={'value': SENSITIVE_TEST_VALUE}
            )
            assert unknown.status_code == 422
            assert unknown.json()['detail'] == [{'loc': ['body', 'value'], 'type': 'value_error'}]
            assert SENSITIVE_TEST_VALUE not in unknown.text

            # DEBUG 不打开内部异常；外层 CORS 对错误响应仍然有效
            for path in ('/_internal', '/_failure'):
                response = await client.get(path)
                assert response.status_code == 500
                assert response.json() == {'code': 'UNKNOWN_ERROR', 'message': '内部服务错误'}
                assert response.headers['Access-Control-Allow-Origin'] == 'https://browser.example'
                assert SENSITIVE_TEST_VALUE not in response.text

    assert 'tests/test_runtime.py:' in ''.join(log_messages)
    assert SENSITIVE_TEST_VALUE not in ''.join(log_messages) + caplog.text


@pytest.mark.parametrize('phase', ['startup', 'shutdown', 'cancel', 'safe'])
async def test_lifecycle_failures_are_safe_and_close_resources(
    phase: Literal['startup', 'shutdown', 'cancel', 'safe'], log_messages: list[str]
) -> None:
    resources: list[Resources] = []
    module_closed: list[bool] = []

    @asynccontextmanager
    async def owner(app: FastAPI) -> AsyncGenerator[None]:
        resource = cast(Resources, app.state.resources)
        resources.append(resource)
        try:
            yield
        finally:
            module_closed.append(not resource.httpx_client.is_closed)
            if phase != 'cancel':
                raise ValueError(f'{SENSITIVE_TEST_VALUE}-cleanup')

    @asynccontextmanager
    async def failing(app: FastAPI) -> AsyncGenerator[None]:
        if phase == 'startup':
            raise RuntimeError(f'{SENSITIVE_TEST_VALUE}-startup')
        if phase == 'cancel':
            raise asyncio.CancelledError(SENSITIVE_TEST_VALUE)
        if phase == 'safe':
            try:
                raise RuntimeError(SENSITIVE_TEST_VALUE)
            except RuntimeError as exc:
                raise SafeValueError('Module configuration is incomplete') from exc
        yield

    # 后一个模块失败时，先前模块和基础资源仍按逆序关闭
    app = create_app(
        make_settings(AUTH_MODULES=['owner', 'failing']),
        auth_module_factories={
            'owner': lambda settings: AuthModule(router=APIRouter(), lifespan=owner),
            'failing': lambda settings: AuthModule(router=APIRouter(), lifespan=failing),
        },
    )
    incoming: asyncio.Queue[Message] = asyncio.Queue()
    incoming.put_nowait({'type': 'lifespan.startup'})
    incoming.put_nowait({'type': 'lifespan.shutdown'})
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    # 经过真实 ASGI lifespan.failed 序列化，不能只验证上下文内抛出的异常
    error_type = {'cancel': asyncio.CancelledError, 'safe': SafeValueError}.get(phase, RuntimeError)
    with pytest.raises(error_type) as failure:
        await app({'type': 'lifespan', 'state': {}}, incoming.get, send)
    if phase != 'cancel':
        expected = {
            'startup': 'Application lifecycle failed',
            'shutdown': 'Resource cleanup failed',
            'safe': 'Module configuration is incomplete',
        }
        assert str(failure.value) == expected[phase]
    failed_type = 'lifespan.shutdown.failed' if phase == 'shutdown' else 'lifespan.startup.failed'
    assert sent[-1]['type'] == failed_type
    assert SENSITIVE_TEST_VALUE not in str(sent) + ''.join(log_messages)
    assert module_closed == [True]
    assert resources[0].httpx_client.is_closed and app.state.resources is None


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
        ('/api/auth/token', 'DELETE'),
        ('/api/users/me', 'GET'),
    ):
        assert (await client.request(method, path)).status_code == 404
    assert not application.app.openapi().get('components', {}).get('securitySchemes')

    # 保留一个不监听的端口，让真实 Redis 连接失败而不模拟其算法
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
