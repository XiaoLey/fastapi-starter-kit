from typing import Annotated, override

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from fastapi.security.utils import get_authorization_scheme_param
from starlette.requests import HTTPConnection

from app.exceptions import ApiError, AuthenticationError
from app.http.deps.request_deps import get_timezone
from app.http.deps.runtime_deps import get_resources, get_settings
from app.models.user import UserModel
from app.services.auth.token_service import validate_token


class OAuth2PasswordBearerWithWebSocket(OAuth2PasswordBearer):
    @override
    async def __call__(self, connection: HTTPConnection) -> str | None:
        scheme, token = get_authorization_scheme_param(connection.headers.get('Authorization'))
        return token if scheme.lower() == 'bearer' and token else None


oauth2_token = OAuth2PasswordBearerWithWebSocket(
    tokenUrl='auth/token/password', scheme_name='PasswordBearer', auto_error=False
)


async def _user_for_token(connection: HTTPConnection, token: str) -> UserModel:
    resources = get_resources(connection)
    payload = await validate_token(token, resources.redis_client, get_settings(connection))

    # 鉴权只持有短会话，WS不能把事务带进整个消息循环
    async with resources.session_factory(info={'time_zone': get_timezone(connection)}) as session:
        user = await session.get(UserModel, payload.sub)
        if user is None or not user.is_enabled():
            raise AuthenticationError()
        return user


async def get_auth_user(connection: HTTPConnection, token: Annotated[str | None, Depends(oauth2_token)]) -> UserModel:
    if token is None:
        raise AuthenticationError()
    return await _user_for_token(connection, token)


async def get_auth_user_dirty(
    connection: HTTPConnection, token: Annotated[str | None, Depends(oauth2_token)]
) -> UserModel | None:
    if token is None:
        return None
    try:
        return await _user_for_token(connection, token)
    except ApiError as exc:
        if exc.status_code != 401:
            raise
        return None


async def get_admin_user(user: Annotated[UserModel, Depends(get_auth_user)]) -> UserModel:
    if not user.is_admin:
        raise ApiError(403, 'PERMISSION_DENIED_ERROR', '权限不足')
    return user


async def require_token(token: Annotated[str | None, Depends(oauth2_token)]) -> str:
    if token is None:
        raise AuthenticationError()
    return token
