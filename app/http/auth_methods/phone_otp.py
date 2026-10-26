from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.http.auth_methods.registration import PhoneCodeRequestSc
from app.http.auth_methods.registration import build_router as registration_router
from app.http.deps import database_deps, firewall_deps, request_deps
from app.http.deps.runtime_deps import get_jwt_settings
from app.schemas.common import BoolSc
from app.schemas.local_auth import VerificationCode, identity_namespace
from app.schemas.token import TokenSc
from app.services.auth import local_auth_service
from app.services.auth.identity_service import PreparedIdentity, resolve_verified_user
from app.services.auth.modules import AuthModule
from app.services.auth.token_service import create_token_response_from_user
from config.settings import Settings


class PhoneLoginSc(PhoneCodeRequestSc):
    verification_code: VerificationCode


def build_module(settings: Settings) -> AuthModule:
    router = APIRouter(prefix='/auth/phone', tags=['手机验证码认证'])

    @router.post('/codes/login', response_model=BoolSc)
    async def code(request: Request, data: PhoneCodeRequestSc) -> BoolSc:
        await local_auth_service.send_contact_code(
            request,
            kind='phone',
            identifier=data.phone,
            purpose='login',
            client_ip=request_deps.get_request_ip(request),
        )
        return BoolSc()

    @router.post('/token', response_model=TokenSc, dependencies=[Depends(firewall_deps.verify_login_limit)])
    async def login(
        request: Request, data: PhoneLoginSc, session: Annotated[AsyncSession, Depends(database_deps.get_db)]
    ) -> TokenSc:
        # 消费证明后只解析这一个已验证身份，不猜测或绑定其他身份
        await local_auth_service.verify_contact_code(
            request, kind='phone', identifier=data.phone, code=data.verification_code, purpose='login'
        )
        identity = PreparedIdentity(
            namespace=identity_namespace('phone'), subject=data.phone, verified_at=datetime.now(UTC)
        )
        user = await resolve_verified_user(session, identity)
        return create_token_response_from_user(user, get_jwt_settings(request))

    return AuthModule(
        'phone_otp',
        router,
        uses_local_tokens=True,
        shared_router=registration_router,
        lifespan=local_auth_service.lifespan,
    )
