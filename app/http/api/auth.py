#
# 鉴权接口
#
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.exception import (
    AuthenticationError,
    InvalidCellphoneCodeError,
    InvalidCellphoneError,
    InvalidEmailCodeError,
    InvalidEmailError,
)
from app.http import deps
from app.schemas.auth import TokenSc, TokenStatusSc
from app.schemas.common import BoolSc
from app.schemas.oauth2 import OAuth2CellphoneSc, OAuth2PasswordSc
from app.schemas.user import UserCreateRecvSc
from app.services.auth import random_code_verifier
from app.services.auth.grant import (
    CellphoneGrant,
    PasswordGrant,
    cancel_grant,
    create_user,
    validate_token,
)
from app.services.email import email_sender
from app.services.sms import sms_sender
from app.support.helper import is_chinese_cellphone, is_valid_email

router = APIRouter(
    prefix='/auth',
    tags=['验证']
)


@router.post('/token/form', response_model=TokenSc,
             name='用户名+密码登录（表单模式）')
async def token_form(request_data: Annotated[OAuth2PasswordRequestForm, Depends()],
                     client_ip: str = Depends(deps.get_request_ip),
                     session: AsyncSession = Depends(deps.get_db)):
    grant = PasswordGrant(session, client_ip, request_data)
    token_data = await grant.respond()
    await session.commit()
    return token_data


@router.post('/token', response_model=TokenSc,
             name='用户名+密码登录（JSON模式）')
async def token(request_data: OAuth2PasswordSc,
                client_ip: str = Depends(deps.get_request_ip),
                session: AsyncSession = Depends(deps.get_db)):
    grant = PasswordGrant(session, client_ip, request_data)
    token_data = await grant.respond()
    await session.commit()
    return token_data


@router.post('/token/admin', response_model=TokenSc,
             name='管理员登录')
async def token_admin(request_data: OAuth2PasswordSc,
                      client_ip: str = Depends(deps.get_request_ip),
                      session: AsyncSession = Depends(deps.get_db)):
    grant = PasswordGrant(session, client_ip, request_data)
    token_data = await grant.respond(is_admin=True)
    await session.commit()
    return token_data


@router.post('/signup', response_model=BoolSc,
             name='注册新用户')
async def signup(user_create: UserCreateRecvSc,
                 client_ip: str = Depends(deps.get_request_ip),
                 session: AsyncSession = Depends(deps.get_db)):
    if not await random_code_verifier.verify(user_create.cellphone, user_create.cellphone_verify_code):
        raise InvalidCellphoneCodeError()

    if user_create.email and not await random_code_verifier.verify(user_create.email, user_create.email_verify_code):
        raise InvalidEmailCodeError()

    await create_user(session, client_ip, user_create)
    await session.commit()
    return BoolSc(success=True)


@router.post('/logout', response_model=BoolSc,
             name='退出登录')
async def logout(token: str = Depends(deps.oauth2_token),
                 client_ip: str = Depends(deps.get_request_ip),
                 session: AsyncSession = Depends(deps.get_db)):
    await cancel_grant(session=session, client_ip=client_ip, token=token)
    await session.commit()
    return BoolSc(success=True)


@router.post('/email/verification_code', response_model=BoolSc,
             name='发送邮箱验证码', description="发送邮箱验证码，验证码在10分钟内有效")
async def send_email_verification_code(email: str = Body(..., embed=True, description="邮箱地址")):
    if not is_valid_email(email, True):
        raise InvalidEmailError()

    code = await random_code_verifier.make(email, 60 * 10)
    await email_sender.send_verification_code(email, code)
    return BoolSc(success=True)


@router.post('/cellphone/token', response_model=TokenSc,
             name='手机号+验证码登录')
async def cellphone_token(request_data: OAuth2CellphoneSc,
                          client_ip: str = Depends(deps.get_request_ip),
                          session: AsyncSession = Depends(deps.get_db)):
    grant = CellphoneGrant(session, client_ip, request_data)
    token_data = await grant.respond()
    await session.commit()
    return token_data


@router.post('/cellphone/verification_code', response_model=BoolSc,
             name='发送手机验证码')
async def send_cellphone_verification_code(cellphone: str = Body(..., embed=True, description="手机号码")):
    if not is_chinese_cellphone(cellphone):
        raise InvalidCellphoneError()

    code = await random_code_verifier.make(cellphone)
    await sms_sender.send_verification_code(cellphone, code)
    return BoolSc(success=True)


@router.post('/token/status', response_model=TokenStatusSc,
             name='查看token状态')
async def token_status(token: str = Depends(deps.oauth2_token)):
    try:
        await validate_token(token)
        return TokenStatusSc(success=True)
    except AuthenticationError as e:
        return TokenStatusSc(success=False, message="Token expired")
    except jwt.ExpiredSignatureError as e:
        return TokenStatusSc(success=False, message="Token expired")
