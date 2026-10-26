"""核心流程测试的共享准备；只清理本次创建的数据库和Redis前缀"""

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import httpx
import pytest
import redis.asyncio as redis
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import URL, pool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.exceptions import EmailSendError, SmsSendError
from app.providers.lifespan_provider import Resources
from app.services.auth.local_auth_service import LocalResources
from app.services.auth.modules import AuthModuleFactory
from bootstrap.application import create_app
from config.settings import PROJECT_ROOT, Settings


class SmsRecorder:
    """仅替代外部供应商，不模拟数据库或验证码算法"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, Literal['register', 'login']]] = []
        self.fail = False
        self.closed = False

    async def send_verification_code(
        self, *, cellphone: str, code: str, purpose: Literal['register', 'login'], expires_in: int
    ) -> None:
        if self.fail:
            raise SmsSendError('Test sender rejected delivery')
        self.sent.append((cellphone, code, purpose))

    async def aclose(self) -> None:
        self.closed = True


class EmailRecorder:
    """仅替代邮件供应商，验证码仍由真实服务生成和验证"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, Literal['register', 'login']]] = []
        self.fail = False
        self.closed = False

    async def send_verification_code(
        self, *, email: str, code: str, purpose: Literal['register', 'login'], expires_in: int
    ) -> None:
        if self.fail:
            raise EmailSendError('Test sender rejected delivery')
        self.sent.append((email, code, purpose))

    async def aclose(self) -> None:
        self.closed = True


def make_settings(**overrides: object) -> Settings:
    return Settings.model_validate({'_env_file': None, 'APP_ENV': 'test', 'REDIS_KEY_PREFIX': 'test-unit', **overrides})


def settings_environment(settings: Settings) -> dict[str, str]:
    """为CLI子进程显式覆盖全部应用字段，避免继承真实dotenv配置"""
    # 将全部字段显式交给子进程；秘密不经过命令行参数
    environment = dict(os.environ)
    for name, value in settings.model_dump().items():
        if isinstance(value, SecretStr):
            environment[name] = value.get_secret_value()
        elif isinstance(value, list):
            environment[name] = json.dumps(value)
        else:
            environment[name] = '' if value is None else str(value)
    return environment


async def migrate(
    url: URL,
    action: Literal['upgrade', 'downgrade', 'check'] = 'upgrade',
    target: str = 'head',
    *,
    cwd: Path = PROJECT_ROOT,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    # 构造隔离配置，不继承真实连接信息
    settings = make_settings(
        POSTGRES_HOST=url.host,
        POSTGRES_PORT=url.port or 5432,
        POSTGRES_DB=url.database,
        POSTGRES_USER=url.username,
        POSTGRES_PASSWORD=url.password or '',
    )

    # 真实CLI隔离当前进程的日志与事件循环，不使用生产测试开关
    args = [sys.executable, '-X', 'utf8', '-m', 'alembic', '-c', str(PROJECT_ROOT / 'alembic.ini'), action]
    if action != 'check':
        args.append(target)
    result = await asyncio.to_thread(
        subprocess.run,
        args,
        cwd=cwd,
        env=settings_environment(settings),
        capture_output=True,
        text=True,
        encoding='utf-8',
        timeout=60,
        check=False,
    )
    if check and result.returncode:
        pytest.fail(f'Alembic {action} failed:\n{result.stdout}\n{result.stderr}')
    return result


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
async def database_url() -> AsyncIterator[URL]:
    raw = os.environ.get('TEST_DATABASE_URL')
    if not raw:
        pytest.skip('Requires explicit TEST_DATABASE_URL')
    control = make_url(raw)
    if (
        control.drivername != 'postgresql+asyncpg'
        or not control.host
        or not control.database
        or not control.database.startswith('fastapi_test_')
    ):
        raise ValueError('Use an explicit postgresql+asyncpg URL naming a fastapi_test_* control database')

    # 不迁移或清空传入control库，只创建随机命名的新库
    name = f'fastapi_test_{uuid4().hex}'
    engine = create_async_engine(control, poolclass=pool.NullPool, hide_parameters=True)
    created = False
    try:
        async with engine.connect() as connection:
            connection = await connection.execution_options(isolation_level='AUTOCOMMIT')
            await connection.exec_driver_sql(f'CREATE DATABASE "{name}" TEMPLATE template0')
            created = True
        yield control.set(database=name)
    finally:
        try:
            if created:
                async with engine.connect() as connection:
                    connection = await connection.execution_options(isolation_level='AUTOCOMMIT')
                    await connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        finally:
            await engine.dispose()


@pytest.fixture
async def integration_settings(database_url: URL) -> AsyncIterator[Settings]:
    raw = os.environ.get('TEST_REDIS_URL')
    if not raw:
        pytest.skip('Requires explicit TEST_REDIS_URL')
    parsed = urlsplit(raw)
    if parsed.scheme != 'redis' or parsed.hostname is None or parsed.username not in (None, '', 'default'):
        raise ValueError('Use an explicit redis:// URL with the default user')

    # 每个组合流程使用独立数据库和Redis命名空间
    prefix = f'test-{uuid4().hex}'
    settings = make_settings(
        POSTGRES_HOST=database_url.host,
        POSTGRES_PORT=database_url.port or 5432,
        POSTGRES_DB=database_url.database,
        POSTGRES_USER=database_url.username,
        POSTGRES_PASSWORD=database_url.password or '',
        REDIS_HOST=parsed.hostname,
        REDIS_PORT=parsed.port or 6379,
        REDIS_DB=parsed.path.strip('/') or '0',
        REDIS_PASSWORD=unquote(parsed.password or ''),
        REDIS_KEY_PREFIX=prefix,
        APP_QPS=1000,
    )
    await migrate(database_url)
    try:
        yield settings
    finally:
        client = redis.Redis.from_url(raw, decode_responses=True)
        try:
            keys = cast(AsyncIterator[str], client.scan_iter(match=f'{prefix}:*', count=100))
            async for key in keys:
                await client.delete(key)
        finally:
            await client.aclose()


@dataclass
class AppClient:
    app: FastAPI
    client: httpx.AsyncClient
    resources: Resources
    sms: SmsRecorder | None
    email: EmailRecorder | None


AppFactory = Callable[..., Awaitable[AppClient]]


@pytest.fixture
async def app_factory(integration_settings: Settings) -> AsyncIterator[AppFactory]:
    async with AsyncExitStack() as stack:

        async def open_app(*, factories: Sequence[AuthModuleFactory] | None = None, **overrides: object) -> AppClient:
            # 所有应用共用本用例的真实服务，选择方式与密钥显式传入
            settings = make_settings(**{
                **integration_settings.model_dump(),
                'JWT_SECRET_KEY': 'test-jwt-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                'AUTH_CODE_SECRET_KEY': 'test-code-key-yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy',
                **overrides,
            })
            app = create_app(
                settings,
                auth_module_factories=factories,
                sms_sender_factory=SmsRecorder,
                email_sender_factory=EmailRecorder,
            )
            await stack.enter_async_context(app.router.lifespan_context(app))
            client = await stack.enter_async_context(
                httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')
            )

            # 仅取实际创建的外部替身，零认证时不制造发送器实例
            local = getattr(app.state, 'local_auth_resources', None)
            sms = local.sms_sender if isinstance(local, LocalResources) else None
            email = local.email_sender if isinstance(local, LocalResources) else None
            assert sms is None or isinstance(sms, SmsRecorder)
            assert email is None or isinstance(email, EmailRecorder)
            return AppClient(app, client, cast(Resources, app.state.resources), sms, email)

        yield open_app
