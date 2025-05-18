#
# 数据库依赖
#

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.http.deps.request import get_timezone
from app.providers import database as db


async def get_db(time_zone: str = Depends(get_timezone)):
    try:
        session: AsyncSession = db.async_session_factory()
        await db.set_session_time_zone(session, time_zone)

        yield session
    finally:
        await session.close()
