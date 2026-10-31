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
    """共享声明式元数据的模型根类，不预设表的生命周期字段"""

    @classmethod
    def get_init_sql_alembic_ddls(cls) -> list[DDL]:
        """返回新库所需的公共数据库对象"""
        return [
            DDL(
                name='tgr_func-update_updated_at_column',
                sql=load_sql('tgr_func-update_updated_at_column.sql'),
                down_sql='DROP FUNCTION IF EXISTS update_updated_at_column;',
            )
        ]

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
    """视图模型的声明基类，不提供表级生命周期字段"""

    __abstract__ = True


class TableModel(Base):
    """带UUID、审计时间和软删除状态的表基类；时间字段写入刷新后可用"""

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
        """按主键读取记录，不隐式排除已归档记录"""
        return await session.get(cls, pk)

    @classmethod
    async def get_one(cls, session: AsyncSession, condition: ColumnElement[bool]) -> Self | None:
        """读取一个匹配记录，不隐式排除已归档记录"""
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
        """返回排除已生效归档记录的查询条件"""
        return sa.or_(cls.deleted_at.is_(None), cls.deleted_at > sa.func.now())

    def is_archived(self) -> bool:
        return self.deleted_at is not None and self.deleted_at <= datetime.datetime.now(datetime.UTC)

    def delete(self) -> None:
        """将记录标记为立即归档，不自行提交事务"""
        self.deleted_at = datetime.datetime.now(datetime.UTC)
