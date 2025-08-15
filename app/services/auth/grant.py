#
# 授权业务
#

import random
import string
from datetime import datetime, timedelta, timezone

import sqlmodel as sm
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.exception import (
    AuthenticationError,
    InsufficientPermissionsError,
    InvalidCellphoneCodeError,
    InvalidPasswordError,
    InvalidUserError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)
from app.models.user import UserModel
from app.providers.database import redis_client
from app.schemas.oauth2 import OAuth2CellphoneSc, OAuth2PasswordSc
from app.schemas.token import TokenSc
from app.schemas.user import UserCreateRecvSc
from app.services.auth import hashing, jwt_helper, random_code_verifier
from app.services.auth.validators import verify_cellphone_availability, verify_username_availability
from config.auth import settings
from config.redis_key import settings as redis_key_settings


def _create_token_response_from_user(user: UserModel):
    expires_delta = timedelta(minutes=settings.JWT_TTL)
    expires_in = int(expires_delta.total_seconds())
    token = jwt_helper.create_access_token(user.id, expires_delta=expires_delta)

    return TokenSc(token_type='bearer', expires_in=expires_in, access_token=token)


async def cancel_grant(session: AsyncSession, client_ip: str, token: str):
    payload = await validate_token(token)
    expire_time = payload.get('exp')
    expire_in = int(expire_time - datetime.now(timezone.utc).timestamp())
    await redis_client.setex(name=f'{redis_key_settings.VERIFY_GRANT_TOKEN}:{token}', time=expire_in, value='invalid')


async def validate_token(token: str) -> dict:
    """
    验证 token 并返回解码后的数据

    :return: 对 token 进行 jwt 解码后的数据（按需获取）
    """
    value = await redis_client.get(f'{redis_key_settings.VERIFY_GRANT_TOKEN}:{token}')
    if value and value == 'invalid':
        raise AuthenticationError()

    payload = jwt_helper.get_payload_by_token(token)

    return payload


async def create_user(session: AsyncSession, client_ip: str, new_user: UserCreateRecvSc):
    """
    创建用户
    """
    # 验证用户名
    await verify_username_availability(session, new_user.username)
    # 验证手机号
    await verify_cellphone_availability(session, new_user.cellphone)

    # 设置密码
    password = None
    if new_user.password:
        password = hashing.get_password_hash(new_user.password)

    # 创建用户
    user = await UserModel(
        **new_user.model_dump(exclude=['password'] + [field for field, value in new_user if value is None]),
        password=password,
    ).create(session)

    return user


class PasswordGrant:
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
        if not (user.password and hashing.verify_password(self.request_data.password, user.password)):
            raise InvalidPasswordError()

        # 用户状态校验
        if not user.is_enabled():
            raise InvalidUserError()

        # 管理员校验
        if is_admin and not await user.is_admin(self.session):
            raise InsufficientPermissionsError()

        return _create_token_response_from_user(user)


class CellphoneGrant:
    def __init__(self, session: AsyncSession, client_ip: str, request_data: OAuth2CellphoneSc):
        self.session = session
        self.client_ip = client_ip
        self.request_data = request_data

    async def respond(self):
        cellphone = self.request_data.cellphone
        code = self.request_data.verification_code

        if not await random_code_verifier.verify(cellphone, code):
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
            except UsernameAlreadyExistsError as e:
                continue
            except Exception as e:
                raise e

        # 用户状态校验
        if not user.is_enabled():
            raise InvalidUserError()

        return _create_token_response_from_user(user)
