import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from dataclasses import dataclass
from typing import cast

import httpx
import redis.asyncio as redis
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.providers import database_provider, httpx_provider, logging_provider, rate_limiter_provider
from app.providers.rate_limiter_provider import Limiter
from app.services.sms.sms_sender import SmsSender
from config.settings import Settings


@dataclass
class Resources:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis_pool: redis.ConnectionPool
    redis_client: redis.Redis
    httpx_client: httpx.AsyncClient
    limiter: Limiter
    sms_sender: SmsSender | None


async def _close_stack(stack: AsyncExitStack) -> None:
    # 二次取消不遗失清理任务；正常资源须支持协作取消
    task = asyncio.create_task(stack.aclose())
    deadline = asyncio.get_running_loop().time() + 10
    cancelled = False
    while not task.done():
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            raise RuntimeError('Resource cleanup timed out')
        try:
            await asyncio.wait_for(asyncio.shield(task), remaining)
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True
        except TimeoutError:
            continue

    task.result()
    if cancelled:
        raise asyncio.CancelledError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = cast(Settings, app.state.settings)
    factory = cast(Callable[[], SmsSender] | None, app.state.sms_sender_factory)
    stack = AsyncExitStack()
    primary: BaseException | None = None
    try:
        # 日志属于进程，不由单个应用退出时关闭
        logging_provider.initialize(settings)
        if settings.SMS_ENABLED and factory is None:
            raise RuntimeError('SMS_ENABLED requires sms_sender_factory')

        # 每创建成功一个资源立即登记，失败路径也执行逆序收尾
        engine = database_provider.create_engine(settings)
        stack.push_async_callback(engine.dispose)
        pool = database_provider.create_redis_pool(settings)
        stack.push_async_callback(pool.aclose)
        redis_client = redis.Redis(connection_pool=pool)
        stack.push_async_callback(redis_client.aclose)
        limiter = rate_limiter_provider.create_limiter(pool, settings.REDIS_KEY_PREFIX)
        stack.push_async_callback(limiter.client.aclose)
        http_client = httpx_provider.create_client()
        stack.push_async_callback(http_client.aclose)

        # 外部适配器先关闭，再关闭其可能使用的HTTP客户端
        sender: SmsSender | None = None
        if settings.SMS_ENABLED and factory is not None:
            try:
                sender = factory()
            except Exception:
                raise RuntimeError('SMS sender initialization failed') from None
            stack.push_async_callback(sender.aclose)
        app.state.resources = Resources(
            engine, database_provider.create_session_factory(engine), pool, redis_client, http_client, limiter, sender
        )
        yield
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            await _close_stack(stack)
        except Exception as exc:
            logging_provider.log_failure(exc)
            if primary is None:
                raise RuntimeError('Resource cleanup failed') from None
        finally:
            app.state.resources = None
