import asyncio
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from dataclasses import dataclass
from typing import cast

import httpx
import redis.asyncio as redis
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.providers import database_provider, httpx_provider, logging_provider, rate_limiter_provider
from app.providers.rate_limiter_provider import Limiter
from app.services.auth.modules import AuthModule
from config.settings import Settings


@dataclass
class Resources:
    """单个应用启动周期拥有的基础资源，不能跨应用共享或退出后复用"""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis_pool: redis.ConnectionPool
    redis_client: redis.Redis
    httpx_client: httpx.AsyncClient
    limiter: Limiter


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
    """为当前应用提供独立资源，正常退出、取消或启动失败均执行收尾"""
    settings = cast(Settings, app.state.settings)
    modules = cast(tuple[AuthModule, ...], app.state.auth_modules)
    stack = AsyncExitStack()
    primary: BaseException | None = None
    try:
        # 日志属于进程，不由单个应用退出时关闭
        logging_provider.initialize(settings)

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

        app.state.resources = Resources(
            engine, database_provider.create_session_factory(engine), pool, redis_client, http_client, limiter
        )

        # 模块资源在基础资源之后创建，退出时先收尾且共享lifespan只运行一次
        started: set[int] = set()
        for module in modules:
            if module.lifespan is not None and id(module.lifespan) not in started:
                started.add(id(module.lifespan))
                await stack.enter_async_context(module.lifespan(app))
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
