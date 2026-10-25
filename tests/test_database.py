from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import migrate

pytestmark = pytest.mark.integration


async def test_legacy_upgrade_and_reversible_data(database_url: URL, tmp_path: Path) -> None:
    # 从其他工作目录迁移，保留旧数据贯穿升级、降级、再次升级
    await migrate(database_url, target='883992f5b42f', cwd=tmp_path)
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    try:
        async with engine.begin() as connection:
            identity = await connection.scalar(
                sa.text(
                    'INSERT INTO users (username,nickname,gender,cellphone,avatar,is_admin) '
                    "VALUES ('legacy','旧账号','unknown','13800000000','',false) RETURNING id"
                )
            )
        await migrate(database_url)
        async with engine.connect() as connection:
            assert await connection.scalar(sa.text('SELECT id FROM users')) == identity
        await migrate(database_url, 'check')

        # 只有全部账号均有手机号时才允许恢复旧schema
        await migrate(database_url, 'downgrade', '883992f5b42f')
        async with engine.connect() as connection:
            assert await connection.scalar(sa.text('SELECT id FROM users')) == identity
            assert (
                await connection.scalar(
                    sa.text(
                        "SELECT is_nullable FROM information_schema.columns WHERE table_name='users' AND column_name='cellphone'"
                    )
                )
                == 'NO'
            )
        await migrate(database_url)
        await migrate(database_url, 'check')
    finally:
        await engine.dispose()


async def test_null_phone_refuses_downgrade_without_changing_data(database_url: URL) -> None:
    await migrate(database_url)
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    try:
        # 绕过ORM默认值，连同无手机号账号一起验证数据库默认值和降级保护
        async with engine.begin() as connection:
            identity = await connection.scalar(
                sa.text(
                    'INSERT INTO users (username,nickname,gender,avatar,is_admin) '
                    "VALUES ('no-phone','未绑定','unknown','',false) RETURNING id"
                )
            )
            revision = await connection.scalar(sa.text('SELECT version_num FROM alembic_version'))
        result = await migrate(database_url, 'downgrade', '883992f5b42f', check=False)
        assert result.returncode != 0 and 'Cannot downgrade' in result.stderr

        # 拒绝发生后，revision、schema和账号必须仍处于可用的head状态
        async with engine.connect() as connection:
            assert await connection.scalar(sa.text('SELECT version_num FROM alembic_version')) == revision
            assert await connection.scalar(sa.text('SELECT id FROM users WHERE cellphone IS NULL')) == identity
            assert (
                await connection.scalar(
                    sa.text(
                        "SELECT is_nullable FROM information_schema.columns WHERE table_name='users' AND column_name='cellphone'"
                    )
                )
                == 'YES'
            )
        await migrate(database_url, 'check')
    finally:
        await engine.dispose()
