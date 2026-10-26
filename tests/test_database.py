from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import migrate

pytestmark = pytest.mark.integration


async def test_fresh_schema_identity_constraints_and_rebuild(database_url: URL, tmp_path: Path) -> None:
    await migrate(database_url, cwd=tmp_path)
    await migrate(database_url, 'check')
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool, hide_parameters=True)
    try:
        # 用户主体没有认证列，默认值和更新时间由真实数据库保证
        async with engine.begin() as connection:
            columns = set(
                (
                    await connection.scalars(
                        sa.text("SELECT column_name FROM information_schema.columns WHERE table_name='users'")
                    )
                ).all()
            )
            assert not {'username', 'cellphone', 'password'}.intersection(columns)
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
        async with engine.begin() as connection:
            after = await connection.scalar(
                sa.text("UPDATE users SET nickname='更新资料' WHERE id=:id RETURNING updated_at"), {'id': first}
            )
            assert after > before

            # 核心不限制每域一身份，域内归属唯一且不同域可重用subject
            await connection.execute(
                sa.text(
                    'INSERT INTO auth_identities(user_id,namespace,subject) VALUES '
                    "(:first,'staff/tenant-a','42'),(:first,'staff/tenant-a','badge-42'),(:second,'staff/tenant-b','42')"
                ),
                {'first': first, 'second': second},
            )
            await connection.execute(
                sa.text("INSERT INTO password_credentials(user_id,password_hash) VALUES (:id,'test-credential')"),
                {'id': first},
            )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO auth_identities(user_id,namespace,subject) VALUES (:id,'staff/tenant-a','42')"
                    ),
                    {'id': second},
                )
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
        await migrate(database_url, cwd=tmp_path)
        await migrate(database_url, 'check')
        async with engine.connect() as connection:
            assert await connection.scalar(sa.text('SELECT count(*) FROM users')) == 0
    finally:
        await engine.dispose()
