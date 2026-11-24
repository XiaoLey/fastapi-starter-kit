import asyncio
import importlib
import pkgutil
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import SchemaItem

from app import models
from app.models.base_model import Base
from config.settings import load_settings
from migrations.support import collect_ddls, install_ddl_compatibility, prepare_schema_migration, register_project_ddls

config = context.config

# 新模型必须在 schema 比较前进入共享 metadata
for module_name in sorted(info.name for info in pkgutil.walk_packages(models.__path__, f'{models.__name__}.')):
    importlib.import_module(module_name)

# 让迁移检查能够报告 DDDL 操作差异
install_ddl_compatibility()

# 用本项目元数据登记迁移所需的附属 DDL
entities, view_names = collect_ddls()
register_project_ddls(entities)

# 离线与在线迁移共用数据库 URL，写入 Alembic 配置时须转义百分号
database_url = load_settings().database_url
config.set_main_option('sqlalchemy.url', database_url.render_as_string(hide_password=False).replace('%', '%%'))

# 按配置文件初始化日志，不禁用已有 logger
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def configure(connection: Connection | None = None) -> None:
    """为在线连接或离线 SQL 输出配置迁移上下文"""

    def include_object(
        obj: SchemaItem, name: str | None, type_: str, reflected: bool, compare_to: SchemaItem | None
    ) -> bool:
        """判断对象是否参与 schema 比较，视图模型不当作表比较"""
        return not (type_ == 'table' and name in view_names)

    context.configure(
        connection=connection,
        url=database_url if connection is None else None,
        target_metadata=Base.metadata,
        literal_binds=connection is None,
        dialect_opts={'paramstyle': 'named'},
        compare_server_default=True,
        include_object=include_object,
        process_revision_directives=prepare_schema_migration,
    )


def do_run_migrations(connection: Connection) -> None:
    """在给定的数据库连接上执行在线迁移"""
    configure(connection)

    # 在线事务边界由 Alembic 管理
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """执行在线迁移并负责清理连接资源"""
    # 不复用迁移连接，SQL 日志隐藏绑定参数
    engine = create_async_engine(database_url, poolclass=pool.NullPool, hide_parameters=True)

    # Alembic 迁移回调使用同步连接
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    # 离线模式只输出 SQL，不建立数据库连接
    configure()

    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_async_migrations())
