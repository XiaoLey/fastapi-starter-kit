import asyncio
from collections.abc import Awaitable
from typing import cast

import sqlalchemy as sa
from fastapi import APIRouter, Request, Response

from app.http.deps.runtime_deps import get_resources
from app.schemas.common import LiveSc, ReadySc

router = APIRouter(tags=['健康检查'])


@router.get('/ping')
async def ping() -> str:
    return 'pong'


@router.get('/health/live', response_model=LiveSc)
async def live() -> LiveSc:
    return LiveSc()


@router.get('/health/ready', response_model=ReadySc, responses={503: {'model': ReadySc}})
async def ready(request: Request, response: Response) -> ReadySc:
    resources = get_resources(request)

    # 探测失败保持不可用状态，不暴露底层异常
    statuses = {'database': 'unavailable', 'redis': 'unavailable'}

    async def probe_database() -> None:
        try:
            async with resources.engine.connect() as connection:
                await connection.execute(sa.text('SELECT 1'))

            # 探测连接正常退出后才标记数据库可用
            statuses['database'] = 'ok'
        except Exception:
            return

    async def probe_redis() -> None:
        try:
            if await cast(Awaitable[bool], resources.redis_client.ping()):
                statuses['redis'] = 'ok'
        except Exception:
            return

    # 两项探测共享就绪检查的时间预算
    tasks = [asyncio.create_task(probe_database()), asyncio.create_task(probe_redis())]
    try:
        async with asyncio.timeout(2):
            await asyncio.gather(*tasks)
    except TimeoutError:
        pass
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

        # 等待驱动收尾，不遗留后台探测
        await asyncio.gather(*tasks, return_exceptions=True)

    # 只有所有依赖都可用时才报告就绪
    is_ready = all(value == 'ok' for value in statuses.values())
    response.status_code = 200 if is_ready else 503
    return ReadySc(status='ready' if is_ready else 'not_ready', **statuses)
