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
        item = RateLimitItemPerSecond(amount, seconds)
        if not await self.strategy.hit(item, *identifiers):
            stats = await self.strategy.get_window_stats(item, *identifiers)
            raise TooManyRequestsError(max(1, math.ceil(stats.reset_time - time.time())))


def create_limiter(pool: redis.ConnectionPool, prefix: str) -> Limiter:
    storage = RedisStorage(
        'async+redis://',
        implementation='redispy',
        key_prefix=f'{prefix}:limits',
        connection_pool=pool,  # pyright: ignore[reportArgumentType]
    )
    bridge = storage.bridge
    if not isinstance(bridge, RedispyBridge):
        raise TypeError('Limiter requires the redispy implementation')
    client = cast(redis.Redis, bridge.get_connection())  # pyright: ignore[reportInvalidCast]
    return Limiter(FixedWindowRateLimiter(storage), client)
