from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from app.http.deps.request_deps import get_timezone
from app.http.deps.runtime_deps import get_resources


async def get_db(
    connection: HTTPConnection, time_zone: Annotated[str, Depends(get_timezone)]
) -> AsyncIterator[AsyncSession]:
    """创建请求会话；业务负责提交，未完成事务在退出时回滚"""
    if connection.scope['type'] != 'http':
        raise RuntimeError('WebSocket operations require short-lived sessions')

    async with get_resources(connection).session_factory(info={'time_zone': time_zone}) as session:
        yield session
