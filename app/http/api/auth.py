#
# 鉴权接口
#

from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.exception import InvalidCellphoneCodeError, InvalidCellphoneError
from app.http import deps
from app.schemas.common import BoolSc
from app.schemas.oauth2 import OAuth2CellphoneSc, OAuth2PasswordSc
from app.schemas.token import TokenSc, TokenStatusSc
from app.schemas.user import UserCreateRecvSc
from app.services.auth import random_code_verifier
from app.services.auth.grant import CellphoneGrant, PasswordGrant
from app.services.auth.token_service import cancel_token, validate_token
from app.services.auth.user_service import create_user
from app.services.sms import sms_sender
from app.support.helper import is_chinese_cellphone

router = APIRouter(prefix='/auth', tags=['认证与授权'])


@router.post('/login', response_model=TokenSc, name='用户名+密码登录')
async def form_login(
    request_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    client_ip: Annotated[str, Depends(deps.get_request_ip)],
    session: Annotated[AsyncSession, Depends(deps.get_db)],
):
    grant = PasswordGrant(session, client_ip, request_data)
    token_data = await grant.respond()
    await session.commit()
    return token_data


@router.post('/login/cellphone', response_model=TokenSc, name='手机号+验证码登录')
async def cellphone_login(
    request_data: OAuth2CellphoneSc,
    client_ip: Annotated[str, Depends(deps.get_request_ip)],
    session: Annotated[AsyncSession, Depends(deps.get_db)],
):
    grant = CellphoneGrant(session, client_ip, request_data)
    token_data = await grant.respond()
    await session.commit()
    return token_data


@router.post('/login/admin', response_model=TokenSc, name='管理员登录')
async def admin_login(
    request_data: OAuth2PasswordSc,
    client_ip: Annotated[str, Depends(deps.get_request_ip)],
    session: Annotated[AsyncSession, Depends(deps.get_db)],
):
    grant = PasswordGrant(session, client_ip, request_data)
    token_data = await grant.respond(is_admin=True)
    await session.commit()
    return token_data


@router.post('/logout', response_model=BoolSc, name='退出登录')
async def logout(token: Annotated[str, Depends(deps.oauth2_token)]):
    await cancel_token(token=token)
    return BoolSc(success=True)


@router.post('/signup', response_model=BoolSc, name='注册新用户')
async def signup(
    user_create: UserCreateRecvSc,
    client_ip: Annotated[str, Depends(deps.get_request_ip)],
    session: Annotated[AsyncSession, Depends(deps.get_db)],
):
    if not await random_code_verifier.verify(user_create.cellphone, user_create.cellphone_verify_code):
        raise InvalidCellphoneCodeError()

    await create_user(session, client_ip, user_create)
    await session.commit()
    return BoolSc(success=True)


@router.post('/verification_code/cellphone', response_model=BoolSc, name='发送手机验证码，验证码在5分钟内有效')
async def send_cellphone_verification_code(cellphone: str = Body(..., embed=True, description='手机号码')):
    if not is_chinese_cellphone(cellphone):
        raise InvalidCellphoneError()

    code = await random_code_verifier.make(cellphone, 60 * 5)
    await sms_sender.send_verification_code(cellphone, code)
    return BoolSc(success=True)


@router.post('/token/status', response_model=TokenStatusSc, name='查看token状态')
async def token_status(token: Annotated[str, Depends(deps.oauth2_token)]):
    payload = await validate_token(token)
    return TokenStatusSc(user_id=payload.sub, expires_at=payload.exp, issued_at=payload.iat, is_valid=True)
