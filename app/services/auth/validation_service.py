#
# 业务逻辑验证器
#
# 存放与数据持久化相关的验证函数，用于检查唯一性、存在性等业务约束。
#

import re

import sqlmodel as sm
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    CellphoneAlreadyExistsError,
    CellphoneEmptyError,
    InvalidCellphoneError,
    InvalidUsernameError,
    InvalidUsernameLengthError,
    UsernameAlreadyExistsError,
    UsernameEmptyError,
)
from app.models.user import UserModel
from app.support.string_helper import is_chinese_cellphone
from config.verify import settings


async def verify_username_availability(session: AsyncSession, username: str, exclude_id: int = None):
    """验证用户名是否可用

    Args:
        session: 数据库会话
        username: 用户名
        exclude_id: 要排除的用户 ID

    Raises:
        UsernameEmptyError: 如果用户名为空
        InvalidUsernameLengthError: 如果用户名长度无效
        InvalidUsernameError: 如果用户名包含无效字符
        UsernameAlreadyExistsError: 如果用户名或手机号已存在
    """
    if not username:
        raise UsernameEmptyError()

    if len(username) < settings.USERNAME_MIN_LENGTH or len(username) > settings.USERNAME_MAX_LENGTH:
        raise InvalidUsernameLengthError()

    if not re.match(settings.USERNAME_PATTERN, username):
        raise InvalidUsernameError()

    query = sm.select(sm.func.count()).where((UserModel.username == username) | (UserModel.cellphone == username))
    if exclude_id:
        query = query.where(UserModel.id != exclude_id)
    result = await session.execute(query)
    if result.scalar() > 0:
        raise UsernameAlreadyExistsError()


async def verify_cellphone_availability(session: AsyncSession, cellphone: str, exclude_id: int = None):
    """验证手机号是否可用

    Args:
        session: 数据库会话
        cellphone: 手机号
        exclude_id: 要排除的用户 ID

    Raises:
        CellphoneEmptyError: 如果手机号为空
        InvalidCellphoneError: 如果手机号格式无效
        CellphoneAlreadyExistsError: 如果手机号已存在
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
