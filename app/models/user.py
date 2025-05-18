import uuid
from typing import Literal

import sqlmodel as sm
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field

from app.models.base_model import TableModel

USER_STATE_TYPE = Literal['disabled', 'enabled']    # 性别
GENDER_TYPE = Literal['male', 'female', 'unknown']  # 用户状态
USER_STATE_PG_TYPE = ENUM(*USER_STATE_TYPE.__args__, name='user_state_type')
GENDER_PG_TYPE = ENUM(*GENDER_TYPE.__args__, name='gender_type')


class UserModel(TableModel, table=True):
    """ 用户表 """
    __tablename__ = 'users'

    username: str = Field(max_length=255, unique=True)                                              # 用户名
    password: str | None = Field(max_length=255)                                                    # 密码
    cellphone: str = Field(default=None, max_length=45, unique=True)                                # 手机号
    email: str | None = Field(default=None, max_length=255, unique=True)                            # 邮箱
    state: USER_STATE_TYPE = Field(default='enabled', sa_type=USER_STATE_PG_TYPE, sa_column_kwargs={'server_default': 'enabled'})  # 用户状态
    nickname: str = Field(min_length=1, max_length=255, sa_type=String(255, collation='zh-x-icu'))  # 昵称
    gender: GENDER_TYPE = Field(default='unknown', sa_type=GENDER_PG_TYPE)                          # 性别
    avatar: str = Field(default='')                                                                 # 头像

    async def is_admin(self, session: AsyncSession):
        result = (await session.scalar(sm.select(sm.exists().where(AdminUserModel.user_id == self.id, AdminUserModel.exist_filter()))))
        return result

    def is_enabled(self):
        return self.state == 'enabled' and not self.is_archived()


class AdminUserModel(TableModel, table=True):
    """ 管理员表 """
    __tablename__ = 'admin_user'

    user_id: uuid.UUID = Field(foreign_key='users.id', unique=True, ondelete='RESTRICT')
