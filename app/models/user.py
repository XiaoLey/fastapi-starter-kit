from typing import get_args

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import TableModel
from app.types import GENDER_TYPE, USER_STATE_TYPE

USER_STATE_PG_TYPE = ENUM(*get_args(USER_STATE_TYPE), name='user_state_type')
GENDER_PG_TYPE = ENUM(*get_args(GENDER_TYPE), name='gender_type')


class UserModel(TableModel):
    """账号标识在全部历史记录中唯一"""

    __tablename__ = 'users'

    nickname: Mapped[str] = mapped_column(sa.String(255, collation='zh-x-icu'))
    username: Mapped[str] = mapped_column(sa.String(255), unique=True)
    password: Mapped[str | None] = mapped_column(sa.String(255), default=None)
    cellphone: Mapped[str | None] = mapped_column(sa.String(45), unique=True, default=None)
    state: Mapped[USER_STATE_TYPE] = mapped_column(USER_STATE_PG_TYPE, default='enabled', server_default='enabled')
    gender: Mapped[GENDER_TYPE] = mapped_column(GENDER_PG_TYPE, default='unknown')
    avatar: Mapped[str] = mapped_column(sa.String, default='')
    is_admin: Mapped[bool] = mapped_column(sa.Boolean, default=False)

    def is_enabled(self) -> bool:
        return self.state == 'enabled' and not self.is_archived()
