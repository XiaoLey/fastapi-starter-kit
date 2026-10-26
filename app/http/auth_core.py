from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.http.deps import auth_deps
from app.http.deps.runtime_deps import get_jwt_settings, get_resources
from app.models.user import UserModel
from app.schemas.common import BoolSc
from app.schemas.token import TokenStatusSc
from app.schemas.user import UserSc
from app.services.auth.token_service import cancel_token, validate_token


def build_router() -> APIRouter:
    """共用本地token与当前用户路由，不属于自动发现的业务API"""
    router = APIRouter(tags=['认证与用户'])

    @router.delete('/auth/token', response_model=BoolSc)
    async def logout(request: Request, token: Annotated[str, Depends(auth_deps.require_token)]) -> BoolSc:
        await cancel_token(token, get_resources(request).redis_client, get_jwt_settings(request))
        return BoolSc()

    @router.get('/auth/token/status', response_model=TokenStatusSc)
    async def status(
        request: Request,
        token: Annotated[str, Depends(auth_deps.require_token)],
        user: Annotated[UserModel, Depends(auth_deps.get_auth_user)],
    ) -> TokenStatusSc:
        payload = await validate_token(token, get_resources(request).redis_client, get_jwt_settings(request))
        return TokenStatusSc(
            user_id=payload.sub,
            expires_at=datetime.fromtimestamp(payload.exp, UTC),
            issued_at=datetime.fromtimestamp(payload.iat, UTC),
        )

    @router.get('/users/me', response_model=UserSc)
    async def me(user: Annotated[UserModel, Depends(auth_deps.get_auth_user)]) -> UserSc:
        return UserSc.model_validate(user)

    return router
