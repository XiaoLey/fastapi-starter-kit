from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.http.deps import auth_deps, database_deps, firewall_deps, request_deps
from app.http.deps.runtime_deps import get_resources, get_settings
from app.schemas.common import BoolSc
from app.schemas.oauth2 import OAuth2CellphoneSc, OAuth2PasswordSc, VerificationCodeReqSc
from app.schemas.token import TokenSc, TokenStatusSc
from app.services.auth import verification_code_service
from app.services.auth.grant_service import CellphoneGrant, PasswordGrant
from app.services.auth.token_service import cancel_token, validate_token

router = APIRouter(prefix='/auth', tags=['认证与授权'])


@router.post('/token/password', response_model=TokenSc, dependencies=[Depends(firewall_deps.verify_login_limit)])
async def login_with_password(
    request: Request,
    request_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(database_deps.get_db)],
) -> TokenSc:
    # 表单中的client/scope仅为兼容输入，不传入权限或持久化层
    try:
        credentials = OAuth2PasswordSc.model_validate({
            'username': request_data.username,
            'password': request_data.password,
            'grant_type': request_data.grant_type or 'password',
        })
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from None
    return await PasswordGrant(session, get_settings(request), credentials).respond()


@router.post('/token/cellphone', response_model=TokenSc, dependencies=[Depends(firewall_deps.verify_login_limit)])
async def login_with_cellphone(
    request: Request, request_data: OAuth2CellphoneSc, session: Annotated[AsyncSession, Depends(database_deps.get_db)]
) -> TokenSc:
    return await CellphoneGrant(
        session, get_resources(request).redis_client, get_settings(request), request_data
    ).respond()


@router.delete('/token', response_model=BoolSc)
async def logout(request: Request, token: Annotated[str, Depends(auth_deps.require_token)]) -> BoolSc:
    await cancel_token(token, get_resources(request).redis_client, get_settings(request))
    return BoolSc()


@router.get('/token/status', response_model=TokenStatusSc)
async def get_token_status(
    request: Request,
    token: Annotated[str, Depends(auth_deps.require_token)],
    user: Annotated[object, Depends(auth_deps.get_auth_user)],
) -> TokenStatusSc:
    payload = await validate_token(token, get_resources(request).redis_client, get_settings(request))
    return TokenStatusSc(
        user_id=payload.sub,
        expires_at=datetime.fromtimestamp(payload.exp, UTC),
        issued_at=datetime.fromtimestamp(payload.iat, UTC),
    )


@router.post('/verification-codes/cellphone', response_model=BoolSc)
async def send_cellphone_verification_code(request: Request, request_data: VerificationCodeReqSc) -> BoolSc:
    resources = get_resources(request)
    await verification_code_service.send_code(
        resources.redis_client,
        resources.limiter,
        get_settings(request),
        resources.sms_sender,
        cellphone=request_data.cellphone,
        purpose=request_data.purpose,
        client_ip=request_deps.get_request_ip(request),
    )
    return BoolSc()
