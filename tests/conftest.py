"""共享测试准备，仅清理本次创建的数据库和 Redis 前缀"""

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
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
from loguru import logger
from pydantic import SecretStr
from sqlalchemy import URL, pool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.exceptions import EmailSendError, SmsSendError
from app.providers.lifespan_provider import Resources
from app.providers.logging_provider import initialize
from app.services.auth.local_auth_service import LocalResources
from app.services.auth.modules import AuthFactory
from bootstrap.application import create_app
from config.settings import PROJECT_ROOT, Settings

SENSITIVE_TEST_VALUE = 'private-test-value-9f6ba532'


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
            raise SmsSendError(f'{SENSITIVE_TEST_VALUE}: {cellphone} {code}')
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
            raise EmailSendError(f'{SENSITIVE_TEST_VALUE}: {email} {code}')
        self.sent.append((email, code, purpose))

    async def aclose(self) -> None:
        self.closed = True


def make_settings(**overrides: object) -> Settings:
    """构造可显式覆盖的测试应用配置"""
    return Settings.model_validate({'_env_file': None, 'APP_ENV': 'test', 'REDIS_KEY_PREFIX': 'test-unit', **overrides})


@pytest.fixture
def log_messages() -> Iterator[list[str]]:
    """收集当前用例的应用日志，用例结束后停止收集"""
    initialize(make_settings())
    messages: list[str] = []
    sink = logger.add(messages.append, format='{message}', diagnose=False, backtrace=False)

    try:
        yield messages
    finally:
        logger.remove(sink)


def settings_environment(settings: Settings) -> dict[str, str]:
    """为 CLI 子进程显式覆盖全部应用字段，避免继承真实 dotenv 配置"""
    # 敏感值经环境变量传递，不进入命令行参数
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
    """执行指定测试库的迁移操作，返回进程结果；默认在失败时中止测试"""
    # 构造隔离配置，不继承真实连接信息
    settings = make_settings(
        POSTGRES_HOST=url.host,
        POSTGRES_PORT=url.port or 5432,
        POSTGRES_DB=url.database,
        POSTGRES_USER=url.username,
        POSTGRES_PASSWORD=url.password or '',
    )

    args = [sys.executable, '-X', 'utf8', '-m', 'alembic', '-c', str(PROJECT_ROOT / 'alembic.ini'), action]
    if action != 'check':
        args.append(target)

    # 迁移进程与测试进程的日志和事件循环相互隔离
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
    """用例期间隔离应用环境变量，保留显式测试服务配置"""
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
async def database_url() -> AsyncIterator[URL]:
    """提供并回收独占的临时数据库；未显式配置测试连接时跳过用例"""
    raw = os.environ.get('TEST_DATABASE_URL')
    if not raw:
        pytest.skip('Requires explicit TEST_DATABASE_URL')

    # 连接前确认控制库是显式命名的测试库
    control = make_url(raw)
    if (
        control.drivername != 'postgresql+asyncpg'
        or not control.host
        or not control.database
        or not control.database.startswith('fastapi_test_')
    ):
        raise ValueError('Use an explicit postgresql+asyncpg URL naming a fastapi_test_* control database')

    # 不迁移或清空控制库，只创建随机命名的新库
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
        # 只销毁本次成功创建的库
        try:
            if created:
                async with engine.connect() as connection:
                    connection = await connection.execution_options(isolation_level='AUTOCOMMIT')
                    await connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        finally:
            # 销毁成功与否都要释放连接资源
            await engine.dispose()


@pytest.fixture
async def integration_settings(database_url: URL) -> AsyncIterator[Settings]:
    """提供已迁移测试库与专用 Redis 前缀的配置，缺少 Redis 测试连接时跳过用例"""
    raw = os.environ.get('TEST_REDIS_URL')
    if not raw:
        pytest.skip('Requires explicit TEST_REDIS_URL')

    parsed = urlsplit(raw)
    if parsed.scheme != 'redis' or parsed.hostname is None or parsed.username not in (None, '', 'default'):
        raise ValueError('Use an explicit redis:// URL with the default user')

    # 将独立测试服务的连接和用例专属前缀写入应用配置
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

    # 在应用配置可用前完成测试库迁移
    await migrate(database_url)

    try:
        yield settings
    finally:
        # 只清理本用例前缀，不清空整个 Redis 数据库
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
    """提供可多次打开应用的工厂，用例结束后关闭全部应用与客户端"""
    async with AsyncExitStack() as stack:

        async def open_app(*, factories: Mapping[str, AuthFactory] | None = None, **overrides: object) -> AppClient:
            """返回已启动的应用与客户端，默认共用本用例的数据库与 Redis 前缀"""
            # 认证能力与密钥来自显式测试配置
            settings = make_settings(**{
                **integration_settings.model_dump(),
                'JWT_SECRET_KEY': 'test-jwt-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                'AUTH_CODE_SECRET_KEY': 'test-code-key-yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy',
                **overrides,
            })

            # 应用生命周期覆盖客户端的整个使用期
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
