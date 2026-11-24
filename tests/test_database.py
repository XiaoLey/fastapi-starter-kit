from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.operations import ops
from alembic.runtime.migration import MigrationContext
from alembic_dddl.src.ops import SyncDDLOp  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.base_model import Base
from app.models.user import UserModel
from migrations.support import prepare_schema_migration
from tests.conftest import migrate


def test_followup_migration_orders_model_ddl_after_table_creation() -> None:
    """后续迁移按表依赖编排附属 DDL，回退不额外清理 enum"""
    # 使用真实 Alembic 操作，复现插件在表比较之前生成附属 DDL 的顺序
    timestamp = datetime.now(UTC)
    shared_ddl = Base.get_init_sql_alembic_ddls()[0]
    attached_ddl = UserModel.get_ext_alembic_ddls()[0]
    shared = SyncDDLOp(shared_ddl, shared_ddl.down_sql, timestamp)
    attached = SyncDDLOp(attached_ddl, attached_ddl.down_sql, timestamp)
    table = ops.CreateTableOp.from_table(Base.metadata.tables[UserModel.__tablename__])
    upgrade = ops.UpgradeOps([shared, attached, table])
    downgrade = upgrade.reverse()
    reversed_table, reversed_attached, reversed_shared = downgrade.ops
    script = ops.MigrationScript('next', upgrade, downgrade)

    # 非初始化迁移同样先建表后建触发器，回退先删触发器且不附加全库 enum 清理
    context = MigrationContext.configure(dialect_name='postgresql')
    prepare_schema_migration(context, ('existing',), [script])
    assert upgrade.ops == [shared, table, attached]
    assert downgrade.ops == [reversed_attached, reversed_table, reversed_shared]


@pytest.mark.integration
async def test_fresh_schema_identity_constraints_and_rebuild(database_url: URL, tmp_path: Path) -> None:
    """空库迁移建立身份约束，完整回退后可无差异重建"""
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool, hide_parameters=True)
    extension_query = sa.text('SELECT extname FROM pg_extension')
    try:
        # 保留迁移前已安装的扩展，作为空库基线
        async with engine.connect() as connection:
            existing_extensions = set((await connection.scalars(extension_query)).all())

        # 初始 schema 必须与模型一致，且不引入额外扩展
        await migrate(database_url, cwd=tmp_path)
        await migrate(database_url, 'check')
        async with engine.connect() as connection:
            assert set((await connection.scalars(extension_query)).all()) == existing_extensions

        # 用户主体表不承载内置认证字段
        async with engine.begin() as connection:
            columns = set(
                (
                    await connection.scalars(
                        sa.text("SELECT column_name FROM information_schema.columns WHERE table_name='users'")
                    )
                ).all()
            )
            assert not {'username', 'cellphone', 'password'}.intersection(columns)

            # 保存初始审计时间，供后续事务验证更新时间触发器
            first = await connection.scalar(
                sa.text(
                    "INSERT INTO users (nickname,gender,avatar,is_admin) VALUES ('用户一','unknown','',false) RETURNING id"
                )
            )
            second = await connection.scalar(
                sa.text(
                    "INSERT INTO users (nickname,gender,avatar,is_admin) VALUES ('用户二','unknown','',false) RETURNING id"
                )
            )
            before = await connection.scalar(sa.text('SELECT updated_at FROM users WHERE id=:id'), {'id': first})

        # 跨事务更新用户时，审计时间必须推进
        async with engine.begin() as connection:
            after = await connection.scalar(
                sa.text("UPDATE users SET nickname='更新资料' WHERE id=:id RETURNING updated_at"), {'id': first}
            )
            assert after > before

            # 同一主体在同域可有多个身份，不同域可复用 subject
            await connection.execute(
                sa.text(
                    'INSERT INTO auth_identities(user_id,namespace,subject) VALUES '
                    "(:first,'staff/tenant-a','42'),(:first,'staff/tenant-a','badge-42'),(:second,'staff/tenant-b','42')"
                ),
                {'first': first, 'second': second},
            )

            # 保留待删除主体的密码凭据，供后续核对级联
            await connection.execute(
                sa.text("INSERT INTO password_credentials(user_id,password_hash) VALUES (:id,'test-credential')"),
                {'id': first},
            )

        # 同域同 subject 不能指向另一个主体
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO auth_identities(user_id,namespace,subject) VALUES (:id,'staff/tenant-a','42')"
                    ),
                    {'id': second},
                )

        # 外键约束拒绝不存在的主体
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text("INSERT INTO auth_identities(user_id,namespace,subject) VALUES (:id,'other','orphan')"),
                    {'id': uuid4()},
                )

        # 可信物理删除级联，不遗留凭据和身份
        async with engine.begin() as connection:
            await connection.execute(sa.text('DELETE FROM users WHERE id=:id'), {'id': first})
            assert await connection.scalar(sa.text('SELECT count(*) FROM auth_identities')) == 1
            assert await connection.scalar(sa.text('SELECT count(*) FROM password_credentials')) == 0

        # 初始化必须完整逆向清理，原生enum不能留到下次建表
        await migrate(database_url, 'downgrade', 'base', cwd=tmp_path)
        async with engine.connect() as connection:
            assert await connection.scalar(sa.text("SELECT to_regclass('users')")) is None
            assert (
                await connection.scalar(
                    sa.text("SELECT count(*) FROM pg_type WHERE typname IN ('gender_type','user_state_type')")
                )
                == 0
            )
            assert await connection.scalar(sa.text("SELECT to_regprocedure('update_updated_at_column()')")) is None

        # 完整回退后仍能从空库重建并保持 schema 无差异
        await migrate(database_url, cwd=tmp_path)
        await migrate(database_url, 'check')
        async with engine.connect() as connection:
            assert await connection.scalar(sa.text('SELECT count(*) FROM users')) == 0
    finally:
        await engine.dispose()
