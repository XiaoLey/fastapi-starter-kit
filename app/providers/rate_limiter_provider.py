import math
import time
from dataclasses import dataclass
from typing import cast

import redis.asyncio as redis
from limits import RateLimitItemPerSecond
from limits.aio.storage import RedisStorage
from limits.aio.storage.redis.redispy import RedispyBridge
from limits.aio.strategies import FixedWindowRateLimiter

from app.exceptions import TooManyRequestsError


@dataclass
class Limiter:
    """固定窗口配额；相同namespace的多个实例共享计数"""

    strategy: FixedWindowRateLimiter
    client: redis.Redis

    async def hit(self, amount: int, seconds: int, *identifiers: str) -> None:
        """尝试消耗指定标识组合的固定窗口配额

        Args:
            amount: 每个窗口的请求配额
            seconds: 窗口时长（秒）
            *identifiers: 组成计数键的有序标识

        Raises:
            TooManyRequestsError: 配额耗尽，异常携带重试等待秒数
        """
        item = RateLimitItemPerSecond(amount, seconds)
        if not await self.strategy.hit(item, *identifiers):
            # 等待时间向上取整，避免提示在当前窗口结束前重试
            stats = await self.strategy.get_window_stats(item, *identifiers)
            raise TooManyRequestsError(max(1, math.ceil(stats.reset_time - time.time())))


def create_limiter(pool: redis.ConnectionPool, prefix: str) -> Limiter:
    """创建使用给定 Redis 连接池的限流器，限流客户端由调用方关闭"""
    storage = RedisStorage(
        'async+redis://',
        implementation='redispy',
        key_prefix=f'{prefix}:limits',
        connection_pool=pool,  # pyright: ignore[reportArgumentType]
    )

    # 生命周期收尾只接管已确认实现的底层客户端
    bridge = storage.bridge
    if not isinstance(bridge, RedispyBridge):
        raise TypeError('Limiter requires the redispy implementation')
    client = cast(redis.Redis, bridge.get_connection())  # pyright: ignore[reportInvalidCast]

    return Limiter(FixedWindowRateLimiter(storage), client)
