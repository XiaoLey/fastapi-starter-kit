import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import Base


class AuthIdentityModel(Base):
    """稳定身份域内的主体归属；用户软删除不释放身份"""

    __tablename__ = 'auth_identities'
    __table_args__ = (
        sa.UniqueConstraint('namespace', 'subject', name='uq_auth_identity_namespace_subject'),
        sa.CheckConstraint('length(namespace) > 0 AND length(subject) > 0', name='ck_auth_identity_nonempty'),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey('users.id', ondelete='CASCADE'), index=True)
    namespace: Mapped[str] = mapped_column(sa.String(128, collation='C'))
    subject: Mapped[str] = mapped_column(sa.String(512, collation='C'))
    verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
    id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID, primary_key=True, default_factory=uuid.uuid4, server_default=sa.text('gen_random_uuid()'), init=False
    )
