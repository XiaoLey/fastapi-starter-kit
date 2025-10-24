from sqlalchemy import String
from sqlalchemy.dialects.postgresql import ENUM
from sqlmodel import Field

from app.models.base_model import TableModel
from app.types import GENDER_TYPE, USER_STATE_TYPE

# 定义 PostgreSQL 枚举类型
USER_STATE_PG_TYPE = ENUM(*USER_STATE_TYPE.__args__, name='user_state_type')
GENDER_PG_TYPE = ENUM(*GENDER_TYPE.__args__, name='gender_type')


class UserModel(TableModel, table=True):
    """用户表"""

    __tablename__ = 'users'

    username: str = Field(max_length=255, unique=True)  # 用户名
    password: str | None = Field(max_length=255)  # 密码
    cellphone: str = Field(default=None, max_length=45, unique=True)  # 手机号
    state: USER_STATE_TYPE = Field(
        default='enabled', sa_type=USER_STATE_PG_TYPE, sa_column_kwargs={'server_default': 'enabled'}
    )  # 用户状态
    nickname: str = Field(min_length=1, max_length=255, sa_type=String(255, collation='zh-x-icu'))  # 昵称
    gender: GENDER_TYPE = Field(default='unknown', sa_type=GENDER_PG_TYPE)  # 性别
    avatar: str = Field(default='')  # 头像路径
    is_admin: bool = Field(default=False)  # 是否管理员

    def is_enabled(self):
        return self.state == 'enabled' and not self.is_archived()
