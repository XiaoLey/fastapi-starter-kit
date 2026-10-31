"""内置本地账号的初始组合注册，不是自定义模块必须遵循的协议"""

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import Field, SecretStr, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ApiError, UserAlreadyExistsError
from app.http.deps import database_deps, firewall_deps, request_deps
from app.schemas.base import BaseSc
from app.schemas.common import BoolSc
from app.schemas.local_auth import Email, Phone, Username, VerificationCode, identity_namespace
from app.schemas.user import UserProfileSc, UserSc
from app.services.auth import identity_service, local_auth_service
from app.services.auth.identity_service import PreparedIdentity
from app.services.auth.modules import AuthModule


class UsernameRegistrationSc(BaseSc):
    kind: Literal['username']
    identifier: Username


class PhoneRegistrationSc(BaseSc):
    kind: Literal['phone']
    identifier: Phone
    verification_code: VerificationCode


class EmailRegistrationSc(BaseSc):
    kind: Literal['email']
    identifier: Email
    verification_code: VerificationCode


class PhoneCodeRequestSc(BaseSc):
    phone: Phone


class EmailCodeRequestSc(BaseSc):
    email: Email


class RegistrationSc(BaseSc):
    """一次创建新账号及本地身份，不能追加到已有账号"""

    identities: list[
        Annotated[UsernameRegistrationSc | PhoneRegistrationSc | EmailRegistrationSc, Field(discriminator='kind')]
    ] = Field(min_length=1, max_length=3)
    password: SecretStr | None = Field(default=None, min_length=12, max_length=128)
    profile: UserProfileSc = Field(default_factory=UserProfileSc)

    @model_validator(mode='after')
    def validate_relationships(self) -> Self:
        kinds = [item.kind for item in self.identities]
        if len(kinds) != len(set(kinds)):
            raise ValueError('Each local identity kind may occur only once')
        if 'username' in kinds and self.password is None:
            raise ValueError('Username registration requires a password')
        return self


def build_router(modules: Sequence[AuthModule]) -> APIRouter:
    """只装配当前内置组合支持的注册及所有权证明入口"""
    options = local_auth_service.local_options(modules)
    router = APIRouter(prefix='/auth', tags=['本地账号注册'])

    @router.post(
        '/register', status_code=201, response_model=UserSc, dependencies=[Depends(firewall_deps.verify_register_limit)]
    )
    async def register(
        request: Request, data: RegistrationSc, session: Annotated[AsyncSession, Depends(database_deps.get_db)]
    ) -> UserSc:
        # 部署能力是授权边界，不允许请求打开未选择的方式
        kinds = {item.kind for item in data.identities}
        if not kinds <= options.registration_identifiers:
            raise ApiError(422, 'REGISTRATION_NOT_SUPPORTED', '包含未启用的注册身份')
        if data.password is not None:
            if not kinds.intersection(options.password_identifiers):
                raise ApiError(422, 'PASSWORD_NOT_SUPPORTED', '此组合不支持密码注册')
        elif not kinds.intersection(options.otp_identifiers):
            raise ApiError(422, 'LOGIN_METHOD_REQUIRED', '注册账号必须有可用的登录方式')

        # 先识别占用；并发下仍由最终数据库唯一约束保证
        for item in data.identities:
            if (
                await identity_service.find_user(
                    session, namespace=identity_namespace(item.kind), subject=item.identifier
                )
                is not None
            ):
                raise UserAlreadyExistsError()

        # 证明只消费一次，后续数据库失败不恢复验证码
        identities: list[PreparedIdentity] = []
        for item in data.identities:
            verified_at: datetime | None = None
            if isinstance(item, (PhoneRegistrationSc, EmailRegistrationSc)):
                await local_auth_service.verify_contact_code(
                    request, kind=item.kind, identifier=item.identifier, code=item.verification_code, purpose='register'
                )
                verified_at = datetime.now(UTC)
            identities.append(
                PreparedIdentity(
                    namespace=identity_namespace(item.kind), subject=item.identifier, verified_at=verified_at
                )
            )

        # 密码模块的凭据参与同一事务，OTP账号不创建空密码行
        writer: Callable[[AsyncSession, UUID], Awaitable[None]] | None = None
        if data.password is not None:
            from app.models.password_credential import PasswordCredentialModel
            from app.support.password_helper import get_password_hash

            password_hash = await get_password_hash(data.password.get_secret_value())

            async def write_password(db: AsyncSession, user_id: UUID) -> None:
                db.add(PasswordCredentialModel(user_id=user_id, password_hash=password_hash))

            writer = write_password
        user = await identity_service.create_account(
            session, identities, profile=data.profile, write_credentials=writer
        )
        return UserSc.model_validate(user)

    # 注册证明不依赖相同通道的OTP登录是否启用
    if 'phone' in options.registration_identifiers:

        @router.post('/phone/codes/register', response_model=BoolSc)
        async def phone_code(request: Request, data: PhoneCodeRequestSc) -> BoolSc:
            await local_auth_service.send_contact_code(
                request,
                kind='phone',
                identifier=data.phone,
                purpose='register',
                client_ip=request_deps.get_request_ip(request),
            )
            return BoolSc()

    if 'email' in options.registration_identifiers:

        @router.post('/email/codes/register', response_model=BoolSc)
        async def email_code(request: Request, data: EmailCodeRequestSc) -> BoolSc:
            await local_auth_service.send_contact_code(
                request,
                kind='email',
                identifier=data.email,
                purpose='register',
                client_ip=request_deps.get_request_ip(request),
            )
            return BoolSc()

    return router
