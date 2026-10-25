import hashlib
import math
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.exceptions import InvalidTokenError
from app.models.user import UserModel
from app.schemas.jwt import JWTSc
from app.schemas.token import TokenSc
from app.support import jwt_helper
from config.settings import Settings


def create_token_response_from_user(user: UserModel, settings: Settings) -> TokenSc:
    return TokenSc(expires_in=settings.JWT_TTL * 60, access_token=jwt_helper.create_access_token(user.id, settings))


def revocation_key(token: str, settings: Settings) -> str:
    return f'{settings.REDIS_KEY_PREFIX}:revoked:{hashlib.sha256(token.encode()).hexdigest()}'


async def validate_token(token: str, redis: Redis, settings: Settings) -> JWTSc:
    """先验签再查询吊销，基础设施故障不当作身份无效"""
    payload = jwt_helper.get_payload_by_token(token, settings)
    if await redis.exists(revocation_key(token, settings)):
        raise InvalidTokenError()
    return payload


async def cancel_token(token: str, redis: Redis, settings: Settings) -> None:
    payload = await validate_token(token, redis, settings)
    remaining = payload.exp - datetime.now(UTC).timestamp()
    await redis.set(revocation_key(token, settings), 'invalid', ex=max(1, math.ceil(remaining)))
