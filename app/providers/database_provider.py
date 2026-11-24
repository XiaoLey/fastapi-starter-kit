import redis.asyncio as redis
import sqlalchemy as sa
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import Connection, event
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, SessionTransaction

from config.settings import Settings


class _Session(Session):
    """仅为本项目会话安装事务局部时区"""


@event.listens_for(_Session, 'after_begin')
def _set_transaction_time_zone(session: _Session, transaction: SessionTransaction, connection: Connection) -> None:
    """为当前事务应用会话时区，未指定时使用默认时区

    Raises:
        TypeError: 会话时区不是字符串
    """
    zone = session.info.get('time_zone', 'Asia/Shanghai')
    if not isinstance(zone, str):
        raise TypeError('Session time zone must be a string')

    # 时区只作用于当前事务，不污染连接池中的后续会话
    connection.execute(sa.text("SELECT set_config('TimeZone', :zone, true)"), {'zone': zone})


def create_engine(settings: Settings) -> AsyncEngine:
    """创建异步数据库引擎，关闭 SQLAlchemy 的绑定参数值展示"""
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
        pool_timeout=settings.POSTGRES_POOL_TIMEOUT,
        pool_recycle=settings.POSTGRES_POOL_RECYCLE,
        hide_parameters=True,
        echo=False,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """创建异步会话工厂；提交事务不会使已加载的对象属性过期"""
    return async_sessionmaker(engine, class_=AsyncSession, sync_session_class=_Session, expire_on_commit=False)


def create_redis_pool(settings: Settings) -> redis.ConnectionPool:
    """创建由调用方关闭的 Redis 连接池，解码 Redis 返回的字节串"""
    return redis.ConnectionPool(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD.get_secret_value() or None,
        decode_responses=True,
        health_check_interval=30,
        socket_connect_timeout=1,
        socket_timeout=1,
        max_connections=64,
    )


def is_dependency_failure(exc: Exception) -> bool:
    """判断异常是否应按依赖暂不可用处理，不把所有数据库错误都视为断连"""
    return isinstance(
        exc, (RedisConnectionError, RedisTimeoutError, ConnectionError, TimeoutError, OperationalError)
    ) or (isinstance(exc, DBAPIError) and exc.connection_invalidated)
