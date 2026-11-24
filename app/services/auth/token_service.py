import hashlib
import math
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.exceptions import InvalidTokenError
from app.models.user import UserModel
from app.schemas.jwt import JWTSc
from app.schemas.token import TokenSc
from app.support import jwt_helper
from config.auth import JwtSettings


def create_token_response_from_user(user: UserModel, settings: JwtSettings) -> TokenSc:
    """签发用户访问凭据，调用方须已确认账号可用及事务成功"""
    return TokenSc(expires_in=settings.JWT_TTL * 60, access_token=jwt_helper.create_access_token(user.id, settings))


def revocation_key(token: str, settings: JwtSettings) -> str:
    """生成不含 token 原文的吊销记录键"""
    return f'{settings.REDIS_KEY_PREFIX}:revoked:{hashlib.sha256(token.encode()).hexdigest()}'


async def validate_token(token: str, redis: Redis, settings: JwtSettings) -> JWTSc:
    """返回有效且未吊销的凭据载荷，不把基础设施故障当作凭据错误"""
    payload = jwt_helper.get_payload_by_token(token, settings)

    # 只为通过签名与声明校验的凭据查询吊销记录
    if await redis.exists(revocation_key(token, settings)):
        raise InvalidTokenError()

    return payload


async def cancel_token(token: str, redis: Redis, settings: JwtSettings) -> None:
    """吊销当前有效凭据，不要求所属用户仍启用；无效或已吊销的凭据被拒绝"""
    payload = await validate_token(token, redis, settings)

    # 吊销记录至少覆盖凭据剩余的有效期
    remaining = payload.exp - datetime.now(UTC).timestamp()
    await redis.set(revocation_key(token, settings), 'invalid', ex=max(1, math.ceil(remaining)))
