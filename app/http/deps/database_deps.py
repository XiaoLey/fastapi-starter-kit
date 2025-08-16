#
# 数据库依赖
#

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.http.deps.request_deps import get_timezone
from app.providers import database_provider as db


async def get_db(time_zone: str = Depends(get_timezone)):
    try:
        session: AsyncSession = db.async_session_factory()
        await db.set_session_time_zone(session, time_zone)

        yield session
    finally:
        await session.close()
