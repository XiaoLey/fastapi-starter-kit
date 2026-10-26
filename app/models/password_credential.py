"""内置密码认证拥有的凭据，不是通用身份的必填部分"""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import Base


class PasswordCredentialModel(Base):
    """用户级密码，由该用户允许的密码登录标识共同使用"""

    __tablename__ = 'password_credentials'

    user_id: Mapped[UUID] = mapped_column(sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    password_hash: Mapped[str] = mapped_column(sa.String(255))
