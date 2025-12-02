import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import TableModel
from app.types import GENDER_TYPE, USER_STATE_TYPE

# 定义 PostgreSQL 枚举类型
USER_STATE_PG_TYPE = ENUM(*USER_STATE_TYPE.__args__, name='user_state_type')
GENDER_PG_TYPE = ENUM(*GENDER_TYPE.__args__, name='gender_type')


class UserModel(TableModel):
    """用户表"""

    __tablename__ = 'users'

    nickname: Mapped[str] = mapped_column(sa.String(255, collation='zh-x-icu')) # 昵称
    username: Mapped[str] = mapped_column(sa.String(255), unique=True)  # 用户名
    password: Mapped[str | None] = mapped_column(sa.String(255), default=None)  # 密码
    cellphone: Mapped[str | None] = mapped_column(sa.String(45), unique=True, default=None)  # 手机号
    state: Mapped[USER_STATE_TYPE] = mapped_column(
        USER_STATE_PG_TYPE, default='enabled', server_default='enabled'
    )  # 用户状态
    gender: Mapped[GENDER_TYPE] = mapped_column(GENDER_PG_TYPE, default='unknown')  # 性别
    avatar: Mapped[str] = mapped_column(sa.String, default='')  # 头像路径
    is_admin: Mapped[bool] = mapped_column(sa.Boolean, default=False)  # 是否管理员

    def is_enabled(self) -> bool:
        return self.state == 'enabled' and not self.is_archived()
