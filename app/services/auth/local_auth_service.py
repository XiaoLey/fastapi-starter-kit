"""内置本地账号的组合能力与发送资源，不参与通用认证模块决策"""

from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import cast

from fastapi import FastAPI
from pydantic import BaseModel, Field, ValidationError, field_validator
from starlette.requests import HTTPConnection

from app.http.deps.runtime_deps import get_resources
from app.schemas.local_auth import ContactKind, LocalKind, identity_namespace
from app.services.auth import verification_code_service
from app.services.auth.modules import AuthModule
from app.services.email.email_sender import EmailSender
from app.services.sms.sms_sender import SmsSender
from config.auth import CodeSettings
from config.settings import Settings


class LocalOptions(BaseModel):
    """内置模块启用的注册标识与登录能力"""

    password_identifiers: list[LocalKind] = Field(default_factory=list)
    otp_identifiers: frozenset[ContactKind] = Field(default_factory=frozenset)

    @field_validator('password_identifiers')
    @classmethod
    def unique_password_identifiers(cls, value: list[LocalKind]) -> list[LocalKind]:
        if len(value) != len(set(value)):
            raise ValueError('Password identifiers must be unique')
        return value

    @property
    def registration_identifiers(self) -> frozenset[LocalKind]:
        return frozenset(self.password_identifiers) | self.otp_identifiers


def local_options(settings: Settings, modules: Sequence[AuthModule]) -> LocalOptions:
    # 只聚合本地模块的贡献，自定义模块即使选用类似ID也不会被误认
    selected = {module.id for module in modules if module.lifespan is lifespan}
    try:
        options = LocalOptions.model_validate({
            'password_identifiers': settings.AUTH_PASSWORD_IDENTIFIERS if 'password' in selected else [],
            'otp_identifiers': [kind for kind in ('phone', 'email') if f'{kind}_otp' in selected],
        })
    except ValidationError:
        raise ValueError('Invalid built-in password identifiers') from None
    if 'password' in selected and not options.password_identifiers:
        raise ValueError('Password module requires at least one identifier')
    return options


@dataclass
class LocalResources:
    options: LocalOptions
    code_settings: CodeSettings | None
    sms_sender: SmsSender | None
    email_sender: EmailSender | None

    @property
    def codes(self) -> CodeSettings:
        if self.code_settings is None:
            raise RuntimeError('Verification codes are not configured')
        return self.code_settings


def get_local_resources(connection: HTTPConnection) -> LocalResources:
    resources = connection.app.state.local_auth_resources
    if not isinstance(resources, LocalResources):
        raise RuntimeError('Local authentication lifespan is not running')
    return resources


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = cast(Settings, app.state.settings)
    modules = cast(tuple[AuthModule, ...], app.state.auth_modules)
    options = local_options(settings, modules)
    contacts = options.registration_identifiers - {'username'}

    # 只有实际需要联系方式证明时才校验验证码密钥和发送器
    codes: CodeSettings | None = None
    if contacts:
        try:
            codes = CodeSettings.model_validate(settings.model_dump())
        except ValidationError:
            raise ValueError('Verification codes require AUTH_CODE_SECRET_KEY') from None
        if codes.AUTH_CODE_SECRET_KEY == settings.JWT_SECRET_KEY:
            raise ValueError('Verification code and JWT secrets must differ')

    async with AsyncExitStack() as stack:
        sms: SmsSender | None = None
        email: EmailSender | None = None
        if 'phone' in contacts:
            sms_factory = cast(Callable[[], SmsSender] | None, app.state.sms_sender_factory)
            if sms_factory is None:
                raise RuntimeError('Phone registration/login requires sms_sender_factory')
            try:
                sms = sms_factory()
            except Exception:
                raise RuntimeError('SMS sender initialization failed') from None
            stack.push_async_callback(sms.aclose)
        if 'email' in contacts:
            email_factory = cast(Callable[[], EmailSender] | None, app.state.email_sender_factory)
            if email_factory is None:
                raise RuntimeError('Email registration/login requires email_sender_factory')
            try:
                email = email_factory()
            except Exception:
                raise RuntimeError('Email sender initialization failed') from None
            stack.push_async_callback(email.aclose)

        # 资源只属于当前应用的当前启动周期
        app.state.local_auth_resources = LocalResources(options, codes, sms, email)
        try:
            yield
        finally:
            app.state.local_auth_resources = None


async def send_contact_code(
    connection: HTTPConnection,
    *,
    kind: ContactKind,
    identifier: str,
    purpose: verification_code_service.Purpose,
    client_ip: str,
) -> None:
    local = get_local_resources(connection)
    resources = get_resources(connection)
    codes = local.codes

    async def deliver(code: str) -> None:
        # 发送器只处理外部交付，不参与验证码状态或身份归属
        if kind == 'phone' and local.sms_sender is not None:
            await local.sms_sender.send_verification_code(
                cellphone=identifier, code=code, purpose=purpose, expires_in=codes.AUTH_CODE_TTL_SECONDS
            )
        elif kind == 'email' and local.email_sender is not None:
            await local.email_sender.send_verification_code(
                email=identifier, code=code, purpose=purpose, expires_in=codes.AUTH_CODE_TTL_SECONDS
            )
        else:
            raise RuntimeError('Required verification sender is not available')

    await verification_code_service.send_code(
        resources.redis_client,
        resources.limiter,
        codes,
        deliver,
        namespace=identity_namespace(kind),
        channel=kind,
        recipient=identifier,
        purpose=purpose,
        client_ip=client_ip,
    )


async def verify_contact_code(
    connection: HTTPConnection,
    *,
    kind: ContactKind,
    identifier: str,
    code: str,
    purpose: verification_code_service.Purpose,
) -> None:
    await verification_code_service.verify_code(
        get_resources(connection).redis_client,
        get_local_resources(connection).codes,
        namespace=identity_namespace(kind),
        channel=kind,
        recipient=identifier,
        code=code,
        purpose=purpose,
    )
