import datetime
import uuid
from typing import Self, override

import sqlalchemy as sa
from alembic_dddl import DDL  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column
from sqlalchemy.sql.elements import ColumnElement

from config.settings import PROJECT_ROOT


def load_sql(filename: str) -> str:
    """读取项目的 PostgreSQL SQL 源"""
    return (PROJECT_ROOT / 'database' / 'postgresql' / filename).read_text(encoding='utf-8')


class Base(AsyncAttrs, MappedAsDataclass, DeclarativeBase):  # pyright: ignore[reportUnsafeMultipleInheritance]
    @classmethod
    def get_init_sql_alembic_ddls(cls) -> list[DDL]:
        # 初始化扩展与公共更新时间触发器
        extensions = ('hstore', 'pg_trgm', 'unaccent', 'uuid-ossp', 'btree_gin', 'btree_gist', 'fuzzystrmatch')
        entities = [
            DDL(
                name=f'ext-{name}',
                sql=f'CREATE EXTENSION IF NOT EXISTS {sql_name};',
                down_sql=f'DROP EXTENSION IF EXISTS {sql_name};',
            )
            for name in extensions
            for sql_name in [f'"{name}"' if '-' in name else name]
        ]
        entities.append(
            DDL(
                name='tgr_func-update_updated_at_column',
                sql=load_sql('tgr_func-update_updated_at_column.sql'),
                down_sql='DROP FUNCTION IF EXISTS update_updated_at_column;',
            )
        )
        return entities

    @classmethod
    def get_ext_alembic_ddls(cls) -> list[DDL]:
        return []

    @classmethod
    def _columns(cls) -> list[object]:
        return [getattr(cls, column.name) for column in cls.__table__.columns]

    def to_dict(self) -> dict[str, object]:
        """返回全部持久化列，不能用作公开账号响应"""
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


class ViewModel(Base):
    __abstract__ = True


class TableModel(Base):
    __abstract__ = True
    __mapper_args__ = {'eager_defaults': True}

    id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID, primary_key=True, default_factory=uuid.uuid4, server_default=sa.text('gen_random_uuid()'), init=False
    )
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), default=None, nullable=False, server_default=sa.func.now(), init=False
    )
    updated_at: Mapped[datetime.datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        default=None,
        nullable=False,
        server_default=sa.func.now(),
        server_onupdate=sa.FetchedValue(),
        init=False,
    )
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), default=None, nullable=True, init=False
    )

    @classmethod
    async def get(cls, session: AsyncSession, pk: uuid.UUID) -> Self | None:
        return await session.get(cls, pk)

    @classmethod
    async def get_one(cls, session: AsyncSession, condition: ColumnElement[bool]) -> Self | None:
        return await session.scalar(sa.select(cls).where(condition).limit(1))

    @classmethod
    @override
    def get_ext_alembic_ddls(cls) -> list[DDL]:
        down_sql = f'DROP TRIGGER IF EXISTS tgr_update_updated_at_column ON {cls.__tablename__};'
        return [
            DDL(
                name=f'tgr-update_updated_at_column_{cls.__tablename__}',
                sql=f'{down_sql}\nCREATE TRIGGER tgr_update_updated_at_column\nBEFORE UPDATE ON {cls.__tablename__}\nFOR EACH ROW\nEXECUTE FUNCTION update_updated_at_column();',
                down_sql=down_sql,
            )
        ]

    @classmethod
    def exist_filter(cls) -> ColumnElement[bool]:
        return sa.or_(cls.deleted_at.is_(None), cls.deleted_at > sa.func.now())

    def is_archived(self) -> bool:
        return self.deleted_at is not None and self.deleted_at <= datetime.datetime.now(datetime.UTC)

    def delete(self) -> None:
        self.deleted_at = datetime.datetime.now(datetime.UTC)
