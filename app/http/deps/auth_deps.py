from typing import Annotated, override

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
from starlette.requests import HTTPConnection

from app.exceptions import ApiError, AuthenticationError
from app.http.deps.request_deps import get_timezone
from app.http.deps.runtime_deps import get_jwt_settings, get_resources
from app.models.user import UserModel
from app.services.auth.token_service import validate_token


class HTTPBearerWithWebSocket(HTTPBearer):
    """从HTTP/WS Authorization头提取Bearer凭据，不负责验签"""

    @override
    async def __call__(self, connection: HTTPConnection) -> HTTPAuthorizationCredentials | None:
        scheme, token = get_authorization_scheme_param(connection.headers.get('Authorization'))
        if scheme.lower() != 'bearer' or not token:
            return None
        return HTTPAuthorizationCredentials(scheme=scheme, credentials=token)


bearer = HTTPBearerWithWebSocket(scheme_name='Bearer', auto_error=False)


async def require_token(
    connection: HTTPConnection, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> str:
    get_jwt_settings(connection)
    if credentials is None:
        raise AuthenticationError()
    return credentials.credentials


async def _user_for_token(connection: HTTPConnection, token: str) -> UserModel:
    resources = get_resources(connection)
    payload = await validate_token(token, resources.redis_client, get_jwt_settings(connection))

    # 鉴权只持有短会话，WS不能把事务带进整个消息循环
    async with resources.session_factory(info={'time_zone': get_timezone(connection)}) as session:
        user = await session.get(UserModel, payload.sub)
        if user is None or not user.is_enabled():
            raise AuthenticationError()
        return user


async def get_auth_user(connection: HTTPConnection, token: Annotated[str, Depends(require_token)]) -> UserModel:
    """返回当前可用用户，结果不持有活动数据库会话"""
    return await _user_for_token(connection, token)


async def get_auth_user_dirty(
    connection: HTTPConnection, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> UserModel | None:
    """缺失或无效凭据返回None，基础设施失败仍向调用方传播"""
    get_jwt_settings(connection)
    if credentials is None:
        return None
    try:
        return await _user_for_token(connection, credentials.credentials)
    except ApiError as exc:
        if exc.status_code != 401:
            raise
        return None


async def get_admin_user(user: Annotated[UserModel, Depends(get_auth_user)]) -> UserModel:
    if not user.is_admin:
        raise ApiError(403, 'PERMISSION_DENIED_ERROR', '权限不足')
    return user
