import asyncio
import hashlib
import hmac
import secrets
from collections.abc import Awaitable
from typing import Literal, cast

from pydantic import TypeAdapter
from redis.asyncio import Redis

from app.exceptions import (
    ApiError,
    DependencyUnavailableError,
    InvalidCellphoneCodeError,
    SmsSendError,
    SmsUnavailableError,
    TooManyRequestsError,
)
from app.providers.rate_limiter_provider import Limiter
from app.services.sms.sms_sender import SmsSender
from app.support.string_helper import numeric_random
from config.settings import Settings

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


def _identity(settings: Settings, cellphone: str, purpose: Purpose) -> str:
    secret = settings.SMS_CODE_SECRET_KEY
    if not settings.SMS_ENABLED or secret is None:
        raise SmsUnavailableError()
    return hmac.new(secret.get_secret_value().encode(), f'{purpose}:{cellphone}'.encode(), hashlib.sha256).hexdigest()


def _digest(settings: Settings, identity: str, generation: str, code: str) -> str:
    secret = settings.SMS_CODE_SECRET_KEY
    if secret is None:
        raise SmsUnavailableError()
    return hmac.new(
        secret.get_secret_value().encode(), f'{identity}:{generation}:{code}'.encode(), hashlib.sha256
    ).hexdigest()


async def send_code(
    redis: Redis,
    limiter: Limiter,
    settings: Settings,
    sender: SmsSender | None,
    *,
    cellphone: str,
    purpose: Purpose,
    client_ip: str,
) -> None:
    """供应商接受且新challenge确认发布后才成功；超时结果可能未知"""
    identity = _identity(settings, cellphone, purpose)
    if sender is None:
        raise SmsUnavailableError()

    # 配额按固定顺序消耗，后续拒绝或发送失败不补偿前面额度
    await limiter.hit(5, 60, 'sms:ip:minute', client_ip)
    await limiter.hit(20, 3600, 'sms:ip:hour', client_ip)
    await limiter.hit(5, 3600, 'sms:phone:hour', identity)
    base = f'{settings.REDIS_KEY_PREFIX}:sms:{identity}'
    owner = secrets.token_hex(16)
    if not await redis.set(f'{base}:cooldown', owner, ex=settings.SMS_SEND_INTERVAL_SECONDS, nx=True):
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
            await sender.send_verification_code(
                cellphone=cellphone, code=code, purpose=purpose, expires_in=settings.SMS_CODE_TTL_SECONDS
            )
        published = await cast(
            Awaitable[object],
            redis.eval(
                _PUBLISH,
                2,
                f'{base}:cooldown',
                f'{base}:challenge',
                owner,
                _digest(settings, identity, owner, code),
                settings.SMS_CODE_TTL_SECONDS,
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
    except (SmsSendError, TimeoutError):
        await release_owned()
        raise ApiError(503, 'SMS_SEND_ERROR', '短信发送未能确认成功') from None
    except Exception:
        await release_owned()
        raise


async def verify_code(redis: Redis, settings: Settings, *, cellphone: str, code: str, purpose: Purpose) -> None:
    """原子验证并消费当前challenge，旧版本操作不影响重发后的状态"""
    identity = _identity(settings, cellphone, purpose)
    key = f'{settings.REDIS_KEY_PREFIX}:sms:{identity}:challenge'
    generation = await cast(Awaitable[str | None], redis.hget(key, 'generation'))
    if generation is None:
        raise InvalidCellphoneCodeError()

    # 比较版本与摘要、累计错误及消费在同一脚本中完成
    result = await cast(
        Awaitable[object],
        redis.eval(
            _CONSUME, 1, key, generation, _digest(settings, identity, generation, code), settings.SMS_CODE_MAX_ATTEMPTS
        ),
    )
    if _INT.validate_python(result) != 1:
        raise InvalidCellphoneCodeError()
