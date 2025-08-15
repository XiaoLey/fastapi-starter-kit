import datetime
import uuid
from pathlib import Path

import sqlmodel as sm
from alembic_dddl import DDL as alembic_DDL
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelConfig

from config.database import settings as db_settings


def load_sql(filename: str) -> str:
    """加载sql脚本"""
    file_path = Path(db_settings.POSTGRESQL_SCRIPTS_DIR) / filename
    return file_path.read_text(encoding='utf-8')


class BaseModel(SQLModel):
    model_config = SQLModelConfig(
        # 参考：https://docs.pydantic.dev/latest/api/config/
        extra='ignore',  # 忽略未知字段
        validate_assignment=True,  # 允许在对象更改时进行数据校验
        from_attributes=True,  # 允许使用类属性填充（而不是只能用字典填充，旧名字叫做 orm_mode）
        populate_by_name=True,  # 允许通过字段名来填充（而不是只能通过别名来填充）
    )

    @classmethod
    def _columns(cls):
        return list(cls.model_fields.keys())

    @classmethod
    def get_init_sql_alembic_ddls(cls):
        """获取表创建前要执行的sql语句"""
        util_schema_list = [
            # 添加 hstore 扩展，支持键值对存储
            alembic_DDL(
                name='ext-hstore',
                sql='CREATE EXTENSION IF NOT EXISTS hstore;',
                down_sql='DROP EXTENSION IF EXISTS hstore;',
            ),
            # 添加 pg_trgm 扩展，用于 trigram 索引以加速文本搜索
            # 主要用于全文搜索，提高 LIKE 和 ILIKE 查询性能
            alembic_DDL(
                name='ext-pg_trgm',
                sql='CREATE EXTENSION IF NOT EXISTS pg_trgm;',
                down_sql='DROP EXTENSION IF EXISTS pg_trgm;',
            ),
            # 添加 unaccent 扩展，用于去除文本中的重音符号
            # 对提高全文搜索的匹配率有帮助，尤其是处理国际化文本时
            alembic_DDL(
                name='ext-unaccent',
                sql='CREATE EXTENSION IF NOT EXISTS unaccent;',
                down_sql='DROP EXTENSION IF EXISTS unaccent;',
            ),
            # 添加 uuid-ossp 扩展，用于生成 UUID
            alembic_DDL(
                name='ext-uuid-ossp',
                sql='CREATE EXTENSION IF NOT EXISTS "uuid-ossp";',
                down_sql='DROP EXTENSION IF EXISTS "uuid-ossp";',
            ),
            # 添加 btree_gin 扩展，用于创建 B-tree 索引的 GIN 索引支持
            alembic_DDL(
                name='ext-btree_gin',
                sql='CREATE EXTENSION IF NOT EXISTS btree_gin;',
                down_sql='DROP EXTENSION IF EXISTS btree_gin;',
            ),
            # 添加 btree_gist 扩展，用于创建 B-tree 索引的 GiST 索引支持
            alembic_DDL(
                name='ext-btree_gist',
                sql='CREATE EXTENSION IF NOT EXISTS btree_gist;',
                down_sql='DROP EXTENSION IF EXISTS btree_gist;',
            ),
            # 添加 fuzzystrmatch 扩展，用于实现模糊字符串匹配，用于实现模糊字符串匹配
            # 这个扩展可以辅助文本相似度分析和匹配
            alembic_DDL(
                name='ext-fuzzystrmatch',
                sql='CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;',
                down_sql='DROP EXTENSION IF EXISTS fuzzystrmatch;',
            ),
            # 触发器函数：更新表的 updated_at 字段
            alembic_DDL(
                name='tgr_func-update_updated_at_column',
                sql=load_sql('tgr_func-update_updated_at_column.sql'),
                down_sql='DROP FUNCTION IF EXISTS update_updated_at_column;',
            ),
        ]

        return util_schema_list

    @classmethod
    def get_ext_alembic_ddls(cls):
        """
        获取扩展alembic的ddl
        """
        return []


class ViewModel(BaseModel):
    __mapper_args__ = {'eager_defaults': True}


class TableModel(BaseModel):
    __mapper_args__ = {'eager_defaults': True}

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        unique=True,
        sa_column_kwargs={'server_default': sm.func.uuid_generate_v4()},
    )
    created_at: datetime.datetime | None = Field(
        default=None,
        nullable=False,
        sa_type=TIMESTAMP(timezone=True),
        sa_column_kwargs={'server_default': sm.func.now()},
    )
    updated_at: datetime.datetime | None = Field(
        default=None,
        nullable=False,
        sa_type=TIMESTAMP(timezone=True),
        sa_column_kwargs={'server_default': sm.func.now(), 'server_onupdate': sm.func.now()},
    )
    deleted_at: datetime.datetime | None = Field(default=None, sa_type=TIMESTAMP(timezone=True))

    @classmethod
    async def get(cls, session: AsyncSession, pk: int):
        return await session.get(cls, pk)

    @classmethod
    async def get_one(cls, session: AsyncSession, filter):
        return await session.scalar(sm.select(cls).where(filter))

    @classmethod
    async def soft_delete_by_id(cls, session: AsyncSession, pk: int):
        await session.execute(sm.update(cls).where(cls.id == pk).values(deleted_at=datetime.now(datetime.timezone.utc)))

    @classmethod
    def get_ext_alembic_ddls(cls):
        down_sql = f'DROP TRIGGER IF EXISTS tgr_update_updated_at_column ON {cls.__tablename__};'
        util_schema_list = super().get_ext_alembic_ddls() + [
            alembic_DDL(
                name=f'tgr-update_updated_at_column_{cls.__tablename__}',
                sql=f"""
                {down_sql}
                CREATE TRIGGER tgr_update_updated_at_column
                BEFORE UPDATE ON {cls.__tablename__}
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();
                """.strip(),
                down_sql=down_sql,
            )
        ]

        return util_schema_list

    @classmethod
    def exist_filter(cls):
        return sm.or_(cls.deleted_at.is_(None), (cls.deleted_at > sm.func.now()))

    async def create(self, session: AsyncSession):
        session.add(self)
        await session.flush()
        return self

    def is_archived(self):
        return self.deleted_at is not None and self.deleted_at <= datetime.now(datetime.timezone.utc)

    async def soft_delete(self, session):
        self.deleted_at = datetime.now(datetime.timezone.utc)
        session.add(self)
        await session.flush()
