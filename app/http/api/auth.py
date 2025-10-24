#
# 鉴权接口
#

from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import InvalidCellphoneError
from app.http.deps import auth_deps, database_deps, request_deps
from app.schemas.common import BoolSc
from app.schemas.oauth2 import OAuth2CellphoneSc
from app.schemas.token import TokenSc, TokenStatusSc
from app.services.auth import verification_code_service
from app.services.auth.grant_service import CellphoneGrant, PasswordGrant
from app.services.auth.token_service import cancel_token, validate_token
from app.services.sms import sms_sender
from app.support.string_helper import is_chinese_cellphone

router = APIRouter(prefix='/auth', tags=['认证与授权'])


@router.post('/token/password', response_model=TokenSc, name='用户名+密码登录')
async def login_with_password(
    request_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    client_ip: Annotated[str, Depends(request_deps.get_request_ip)],
    session: Annotated[AsyncSession, Depends(database_deps.get_db)],
):
    grant = PasswordGrant(session, client_ip, request_data)
    token_data = await grant.respond()
    return token_data


@router.post('/token/cellphone', response_model=TokenSc, name='手机号+验证码登录')
async def login_with_cellphone(
    request_data: OAuth2CellphoneSc,
    client_ip: Annotated[str, Depends(request_deps.get_request_ip)],
    session: Annotated[AsyncSession, Depends(database_deps.get_db)],
):
    grant = CellphoneGrant(session, client_ip, request_data)
    token_data = await grant.respond()
    if grant.is_creating_user:
        await session.commit()
    return token_data


@router.delete('/token', response_model=BoolSc, name='退出登录')
async def logout(token: Annotated[str, Depends(auth_deps.oauth2_token)]):
    await cancel_token(token=token)
    return BoolSc(success=True)


@router.get('/token/status', response_model=TokenStatusSc, name='查看当前token状态')
async def get_token_status(token: Annotated[str, Depends(auth_deps.oauth2_token)]):
    payload = await validate_token(token)
    return TokenStatusSc(user_id=payload.sub, expires_at=payload.exp, issued_at=payload.iat, is_valid=True)


@router.post('/verification-codes/cellphone', response_model=BoolSc, name='发送手机验证码')
async def send_cellphone_verification_code(cellphone: str = Body(..., embed=True, description='手机号码')):
    if not is_chinese_cellphone(cellphone):
        raise InvalidCellphoneError()

    code = await verification_code_service.make_code(cellphone, 60 * 5)
    await sms_sender.send_verification_code(cellphone, code)
    return BoolSc(success=True)
