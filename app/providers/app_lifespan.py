from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi_limiter import FastAPILimiter

import app.providers.rate_limiter as rate_limiter
from app.providers.database import async_session_factory, redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化限流器
    await FastAPILimiter.init(redis_client,
                              identifier=rate_limiter.default_identifier,
                              http_callback=rate_limiter.http_default_callback,
                              ws_callback=rate_limiter.ws_default_callback)
    # This hook ensures that a connection is opened to handle any queries
    yield
    # This hook ensures that the connection is closed when we've finished processing the request.

    # 关闭限流器
    await FastAPILimiter.close()

    await async_session_factory().close_all()

    if redis_client:
        await redis_client.close()
