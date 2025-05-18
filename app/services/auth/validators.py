import re

import sqlmodel as sm
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.exception import (
    CellphoneAlreadyExistsError,
    CellphoneEmptyError,
    EmailAlreadyExistsError,
    EmailEmptyError,
    InvalidCellphoneError,
    InvalidEmailError,
    InvalidUsernameError,
    InvalidUsernameLengthError,
    UsernameAlreadyExistsError,
    UsernameEmptyError,
)
from app.models.user import UserModel
from app.support.helper import is_chinese_cellphone, is_valid_email
from config.verify import settings


async def verify_username_availability(session: AsyncSession, username: str, exclude_id: int = None):
    """
    验证用户名是否可用

    :param username: 用户名
    :param exclude_id: 排除的用户 ID
    """
    if not username:
        raise UsernameEmptyError()

    if len(username) < settings.USERNAME_MIN_LENGTH or len(username) > settings.USERNAME_MAX_LENGTH:
        raise InvalidUsernameLengthError()

    if not re.match(settings.USERNAME_PATTERN, username):
        raise InvalidUsernameError()

    query = sm.select(sm.func.count()).where(
        (UserModel.username == username) |
        (UserModel.email == username) |
        (UserModel.cellphone == username))
    if exclude_id:
        query = query.where(UserModel.id != exclude_id)
    result = await session.execute(query)
    if result.scalar() > 0:
        raise UsernameAlreadyExistsError()


async def verify_cellphone_availability(session: AsyncSession, cellphone: str,  exclude_id: int = None):
    """
    验证手机号是否可用

    :param cellphone: 手机号
    :param exclude_id: 排除的用户 ID
    """
    if not cellphone:
        raise CellphoneEmptyError()

    if not is_chinese_cellphone(cellphone):
        raise InvalidCellphoneError()

    query = sm.select(sm.func.count()).where(UserModel.cellphone == cellphone)
    if exclude_id:
        query = query.where(UserModel.id != exclude_id)
    result = await session.execute(query)
    if result.scalar() > 0:
        raise CellphoneAlreadyExistsError()


async def verify_email_availability(session: AsyncSession, email: str, exclude_id: int = None):
    """
    验证邮箱是否可用

    :param email: 邮箱
    :param exclude_id: 排除的用户 ID
    """
    if not email:
        raise EmailEmptyError()

    if not is_valid_email(email):
        raise InvalidEmailError()

    query = sm.select(sm.func.count()).where(UserModel.email == email)
    if exclude_id:
        query = query.where(UserModel.id != exclude_id)
    result = await session.execute(query)
    if result.scalar() > 0:
        raise EmailAlreadyExistsError()
