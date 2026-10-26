import asyncio
import hashlib
import hmac
import json
import secrets
from collections.abc import Awaitable, Callable
from typing import Literal, cast

from pydantic import TypeAdapter
from redis.asyncio import Redis

from app.exceptions import (
    ApiError,
    DependencyUnavailableError,
    EmailSendError,
    InvalidVerificationCodeError,
    SmsSendError,
    TooManyRequestsError,
)
from app.providers.rate_limiter_provider import Limiter
from app.support.string_helper import numeric_random
from config.auth import CodeSettings

Purpose = Literal['register', 'login']
_INT = TypeAdapter(int)
_RELEASE = "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0"
_PUBLISH = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('HSET', KEYS[2], 'generation', ARGV[1], 'digest', ARGV[2], 'attempts', 0)
redis.call('EXPIRE', KEYS[2], ARGV[3])
return 1
"""
_CONSUME = """
if redis.call('HGET', KEYS[1], 'generation') ~= ARGV[1] then return 0 end
if redis.call('HGET', KEYS[1], 'digest') == ARGV[2] then
    redis.call('DEL', KEYS[1])
    return 1
end
local attempts = redis.call('HINCRBY', KEYS[1], 'attempts', 1)
if attempts >= tonumber(ARGV[3]) then redis.call('DEL', KEYS[1]) end
return 0
"""


def _identity(settings: CodeSettings, namespace: str, channel: str, recipient: str, purpose: Purpose) -> str:
    message = json.dumps(
        [settings.REDIS_KEY_PREFIX, namespace, channel, purpose, recipient], separators=(',', ':'), ensure_ascii=True
    )
    return hmac.new(
        settings.AUTH_CODE_SECRET_KEY.get_secret_value().encode(), message.encode(), hashlib.sha256
    ).hexdigest()


def _digest(settings: CodeSettings, identity: str, generation: str, code: str) -> str:
    return hmac.new(
        settings.AUTH_CODE_SECRET_KEY.get_secret_value().encode(),
        f'{identity}:{generation}:{code}'.encode(),
        hashlib.sha256,
    ).hexdigest()


async def send_code(
    redis: Redis,
    limiter: Limiter,
    settings: CodeSettings,
    deliver: Callable[[str], Awaitable[None]],
    *,
    namespace: str,
    channel: str,
    recipient: str,
    purpose: Purpose,
    client_ip: str,
) -> None:
    """供应商接受且新challenge确认发布后才成功；超时结果可能未知

    Args:
        deliver: 接收新验证码的交付回调，正常返回表示供应商已接受
        namespace: 身份归属域，与应用Redis前缀分别隔离
        channel: 验证通道标识
        recipient: 已由所属模块规范化的接收者
    """
    identity = _identity(settings, namespace, channel, recipient, purpose)

    # 配额按固定顺序消耗，后续拒绝或发送失败不补偿前面额度
    await limiter.hit(5, 60, 'auth-code:ip:minute', client_ip)
    await limiter.hit(20, 3600, 'auth-code:ip:hour', client_ip)
    await limiter.hit(5, 3600, 'auth-code:recipient:hour', identity)
    base = f'{settings.REDIS_KEY_PREFIX}:auth-code:{identity}'
    owner = secrets.token_hex(16)
    if not await redis.set(f'{base}:cooldown', owner, ex=settings.AUTH_CODE_SEND_INTERVAL_SECONDS, nx=True):
        ttl = _INT.validate_python(
            await cast(Awaitable[object], redis.eval("return redis.call('TTL', KEYS[1])", 1, f'{base}:cooldown'))
        )
        raise TooManyRequestsError(ttl)

    async def release_owned() -> None:
        # 清理失败不能吞掉原始取消或供应商异常，更不能清除challenge
        try:
            await cast(Awaitable[object], redis.eval(_RELEASE, 1, f'{base}:cooldown', owner))
        except Exception:
            return

    # 新码发布前旧码仍有效，所有晚到操作都要比较占位归属
    code = numeric_random(6)
    try:
        async with asyncio.timeout(10):
            await deliver(code)
        published = await cast(
            Awaitable[object],
            redis.eval(
                _PUBLISH,
                2,
                f'{base}:cooldown',
                f'{base}:challenge',
                owner,
                _digest(settings, identity, owner, code),
                settings.AUTH_CODE_TTL_SECONDS,
            ),
        )
        if _INT.validate_python(published) != 1:
            raise DependencyUnavailableError()
    except asyncio.CancelledError:
        cleanup = asyncio.create_task(release_owned())
        try:
            await asyncio.shield(cleanup)
        finally:
            if not cleanup.done():
                cleanup.cancel()
                await asyncio.gather(cleanup, return_exceptions=True)
        raise
    except (SmsSendError, EmailSendError, TimeoutError):
        await release_owned()
        raise ApiError(503, 'CODE_SEND_ERROR', '验证码发送未能确认成功') from None
    except Exception:
        await release_owned()
        raise


async def verify_code(
    redis: Redis, settings: CodeSettings, *, namespace: str, channel: str, recipient: str, code: str, purpose: Purpose
) -> None:
    """原子验证并消费当前代验证码；旧版本操作不影响重发后的状态

    Args:
        recipient: 已由所属模块规范化的接收者，规则须与发送时一致

    Raises:
        InvalidVerificationCodeError: 验证码错误、过期或已消费
    """
    identity = _identity(settings, namespace, channel, recipient, purpose)
    key = f'{settings.REDIS_KEY_PREFIX}:auth-code:{identity}:challenge'
    generation = await cast(Awaitable[str | None], redis.hget(key, 'generation'))
    if generation is None:
        raise InvalidVerificationCodeError()

    # 比较版本与摘要、累计错误及消费在同一脚本中完成
    result = await cast(
        Awaitable[object],
        redis.eval(
            _CONSUME, 1, key, generation, _digest(settings, identity, generation, code), settings.AUTH_CODE_MAX_ATTEMPTS
        ),
    )
    if _INT.validate_python(result) != 1:
        raise InvalidVerificationCodeError()
