from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from pydantic import ValidationError

from app.exceptions import InvalidTokenError, TokenExpiredError
from app.schemas.jwt import JWTSc
from config.auth import JwtSettings

_RESERVED = frozenset({'iss', 'aud', 'sub', 'exp', 'nbf', 'iat', 'jti'})


def create_access_token(
    subject: UUID,
    settings: JwtSettings,
    *,
    expires_delta: timedelta | None = None,
    additional_claims: dict[str, object] | None = None,
) -> str:
    """为指定主体签发访问凭据

    Args:
        expires_delta: 自签发起算的有效期；省略时使用配置值
        additional_claims: 可 JSON 序列化的额外声明

    Raises:
        ValueError: 额外声明与保留声明冲突
    """
    if additional_claims and _RESERVED.intersection(additional_claims):
        raise ValueError('Additional claims cannot replace reserved claims')

    # 所有时间声明以同一个 UTC 时刻为基准
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        'iss': settings.JWT_ISSUER,
        'aud': settings.JWT_AUDIENCE,
        'sub': str(subject),
        'exp': now + (expires_delta if expires_delta is not None else timedelta(minutes=settings.JWT_TTL)),
        'nbf': now,
        'iat': now,
        'jti': str(uuid4()),
        **(additional_claims or {}),
    }

    return jwt.encode(payload, settings.JWT_SECRET_KEY.get_secret_value(), algorithm='HS256')


def get_payload_by_token(token: str, settings: JwtSettings) -> JWTSc:
    """返回已验签且通过必需声明校验的访问凭据声明

    Raises:
        TokenExpiredError: 凭据被判定为过期
        InvalidTokenError: 凭据未通过其他校验
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=['HS256'],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={'require': sorted(_RESERVED)},
        )

        # 验签通过的声明仍须符合应用的数据约束
        return JWTSc.model_validate(payload)
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError() from None
    except (jwt.InvalidTokenError, ValidationError, ValueError, TypeError):
        raise InvalidTokenError() from None
