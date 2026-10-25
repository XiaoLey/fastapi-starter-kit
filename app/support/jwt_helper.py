from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from pydantic import ValidationError

from app.exceptions import InvalidTokenError, TokenExpiredError
from app.schemas.jwt import JWTSc
from config.settings import Settings

_RESERVED = frozenset({'iss', 'aud', 'sub', 'exp', 'nbf', 'iat', 'jti'})


def create_access_token(
    subject: UUID,
    settings: Settings,
    *,
    expires_delta: timedelta | None = None,
    additional_claims: dict[str, object] | None = None,
) -> str:
    """签发访问凭据，额外声明不能覆盖保留字段"""
    if additional_claims and _RESERVED.intersection(additional_claims):
        raise ValueError('Additional claims cannot replace reserved claims')

    # 所有时间声明共用同一个UTC时刻
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


def get_payload_by_token(token: str, settings: Settings) -> JWTSc:
    """验签并校验必需声明，所有凭据错误均属于身份错误"""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=['HS256'],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={'require': sorted(_RESERVED)},
        )
        return JWTSc.model_validate(payload)
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError() from None
    except (jwt.InvalidTokenError, ValidationError, ValueError, TypeError):
        raise InvalidTokenError() from None
