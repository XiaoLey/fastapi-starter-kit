#
# 鉴权依赖
#

from typing import Optional
from uuid import UUID

import sqlmodel as sm
from fastapi import Depends, HTTPException, Request, WebSocket
from fastapi.requests import HTTPConnection
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.exception import AuthenticationError, InvalidUserError
from app.http.deps.database import get_db
from app.models.user import UserModel
from app.services.auth.grant import validate_token
from config.config import settings as config_settings


class HvOAuth2PasswordBearer(OAuth2PasswordBearer):
    async def __call__(self, request_or_ws: HTTPConnection) -> Optional[str]:
        if isinstance(request_or_ws, Request):
            token = await super().__call__(request_or_ws)
        elif isinstance(request_or_ws, WebSocket):
            token = request_or_ws.query_params.get("access_token")
            if not token:
                raise AuthenticationError()
        else:
            raise AuthenticationError()

        return token


oauth2_token = HvOAuth2PasswordBearer(
    tokenUrl=f"{config_settings.API_PREFIX[1:]}/auth/token/form",
)


async def get_auth_user(token: str = Depends(oauth2_token),
                        session: AsyncSession = Depends(get_db)) -> UserModel:
    payload = await validate_token(token)
    user_id = UUID(payload.get('sub'))
    user = (await session.execute(sm.select(UserModel).where(UserModel.id == user_id))).scalar()

    if not user:
        raise AuthenticationError()
    if not user.is_enabled():
        raise InvalidUserError()
    return user


async def get_auth_user_dirty(request_or_ws: HTTPConnection, session: AsyncSession = Depends(get_db)) -> UserModel | None:
    try:
        token: str = await oauth2_token(request_or_ws)
    except HTTPException as e:
        return None

    try:
        payload = await validate_token(token)
    except Exception as e:
        return None

    user_uuid = UUID(payload.get('sub'))
    user = (await session.execute(sm.select(UserModel).where(UserModel.id == user_uuid))).scalar()
    return user
