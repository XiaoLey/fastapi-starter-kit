#
# OAuth2 授权业务逻辑
#
# 实现用户名密码授权和手机号授权的业务逻辑，包括用户验证和令牌颁发。
#

import random
import string

import sqlmodel as sm
from pydantic import ConfigDict, validate_call
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    InsufficientPermissionsError,
    InvalidCellphoneCodeError,
    InvalidPasswordError,
    InvalidUserError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)
from app.models.user import UserModel
from app.schemas.oauth2 import OAuth2CellphoneSc, OAuth2PasswordSc
from app.schemas.user import UserCreateRecvSc
from app.services.auth import verification_code_service
from app.services.auth.token_service import create_token_response_from_user
from app.services.auth.user_service import create_user
from app.support import password_helper


class PasswordGrant:
    """用户名密码授权"""

    @validate_call(config=ConfigDict(arbitrary_types_allowed=True))
    def __init__(self, session: AsyncSession, client_ip: str, request_data: OAuth2PasswordSc):
        self.session = session
        self.client_ip = client_ip
        self.request_data = request_data

    async def respond(self, is_admin: bool = False):
        user = await UserModel.get_one(
            self.session,
            sm.or_(UserModel.username == self.request_data.username, UserModel.cellphone == self.request_data.username),
        )
        if not user:
            raise UserNotFoundError()

        # 用户密码校验
        if not (user.password and password_helper.verify_password(self.request_data.password, user.password)):
            raise InvalidPasswordError()

        # 用户状态校验
        if not user.is_enabled():
            raise InvalidUserError()

        # 管理员校验
        if is_admin and not await user.is_admin(self.session):
            raise InsufficientPermissionsError()

        return create_token_response_from_user(user)


class CellphoneGrant:
    """手机号授权"""

    def __init__(self, session: AsyncSession, client_ip: str, request_data: OAuth2CellphoneSc):
        self.session = session
        self.client_ip = client_ip
        self.request_data = request_data

    async def respond(self):
        cellphone = self.request_data.cellphone
        code = self.request_data.verification_code

        if not await verification_code_service.verify(cellphone, code):
            raise InvalidCellphoneCodeError()

        user = await UserModel.get_one(self.session, UserModel.cellphone == cellphone)
        while not user:
            try:
                # 创建一个用户名（随机 10 位数字或字母组合）
                username = ''.join(random.choices(string.digits + string.ascii_lowercase, k=10))

                # 创建用户
                new_user_info = UserCreateRecvSc(
                    username=username,
                    password=None,
                    nickname=username,
                    gender='unknown',
                    cellphone=cellphone,
                    cellphone_verify_code='',
                )
                user = await create_user(self.session, self.client_ip, new_user_info)
            except UsernameAlreadyExistsError:
                continue
            except Exception as e:
                raise e

        # 用户状态校验
        if not user.is_enabled():
            raise InvalidUserError()

        return create_token_response_from_user(user)
