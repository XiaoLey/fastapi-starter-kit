from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import Field, SecretStr, TypeAdapter, ValidationInfo, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ApiError, AuthenticationError
from app.http.auth_methods.registration import build_router as registration_router
from app.http.deps import database_deps, firewall_deps
from app.http.deps.runtime_deps import get_jwt_settings
from app.models.password_credential import PasswordCredentialModel
from app.schemas.base import BaseSc
from app.schemas.local_auth import Email, LocalKind, Phone, Username, identity_namespace
from app.schemas.token import TokenSc
from app.services.auth import identity_service, local_auth_service
from app.services.auth.modules import AuthModule
from app.services.auth.token_service import create_token_response_from_user
from app.support.password_helper import verify_password
from config.settings import Settings

_IDENTIFIERS = {'username': TypeAdapter(Username), 'phone': TypeAdapter(Phone), 'email': TypeAdapter(Email)}


class PasswordLoginSc(BaseSc):
    """显式指定标识种类，密码不去首尾空白"""

    kind: LocalKind
    identifier: str = Field(min_length=1, max_length=512)
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator('identifier')
    @classmethod
    def normalize_identifier(cls, value: str, info: ValidationInfo) -> str:
        kind = info.data.get('kind')
        if kind not in _IDENTIFIERS:
            raise ValueError('A valid identity kind is required')
        return _IDENTIFIERS[kind].validate_python(value)


def build_module(settings: Settings) -> AuthModule:
    router = APIRouter(prefix='/auth/password', tags=['密码认证'])

    @router.post('/token', response_model=TokenSc, dependencies=[Depends(firewall_deps.verify_login_limit)])
    async def login(
        request: Request, data: PasswordLoginSc, session: Annotated[AsyncSession, Depends(database_deps.get_db)]
    ) -> TokenSc:
        if data.kind not in local_auth_service.get_local_resources(request).options.password_identifiers:
            raise ApiError(422, 'PASSWORD_IDENTITY_NOT_SUPPORTED', '未启用此密码登录标识')

        # 不因缺账号或缺凭据跳过密码计算
        user = await identity_service.find_user(
            session, namespace=identity_namespace(data.kind), subject=data.identifier
        )
        credential = await session.get(PasswordCredentialModel, user.id) if user is not None else None
        valid, replacement = await verify_password(
            data.password.get_secret_value(), credential.password_hash if credential is not None else None
        )
        if user is None or credential is None or not valid or not user.is_enabled():
            raise AuthenticationError()

        # 哈希参数升级提交成功之后才能签发凭据
        if replacement is not None:
            credential.password_hash = replacement
            await session.commit()
        return create_token_response_from_user(user, get_jwt_settings(request))

    return AuthModule(
        'password',
        router,
        uses_local_tokens=True,
        shared_router=registration_router,
        lifespan=local_auth_service.lifespan,
    )
