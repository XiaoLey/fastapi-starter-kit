import redis.asyncio as redis
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.providers.sqlalchemy_provider  # noqa: F401
from config.config import settings as config_settings
from config.database import redis_settings
from config.database import settings as db_settings

engine = create_async_engine(
    db_settings.SQLALCHEMY_DATABASE_URL,
    pool_size=4,
    # echo_pool='debug' if config_settings.DEBUG else False,
    echo='debug' if config_settings.DEBUG else False,
)


# 异步数据库会话
async_session_factory = async_sessionmaker(
    autocommit=False, autoflush=True, bind=engine, class_=AsyncSession, expire_on_commit=False
)


async def set_session_time_zone(session: AsyncSession, time_zone: str = 'Asia/Shanghai') -> None:
    await session.execute(sa.text(f"SET TIME ZONE '{time_zone}'"))


# redis
redis_pool = redis.ConnectionPool(
    host=redis_settings.REDIS_HOST,
    port=redis_settings.REDIS_PORT,
    db=redis_settings.REDIS_DB,
    password=redis_settings.REDIS_PASSWORD,
    decode_responses=True,
    health_check_interval=30,  # 每30秒检查一次连接健康状态，防止使用失效连接
)
redis_client = redis.Redis(connection_pool=redis_pool)
