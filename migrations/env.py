def setup_encoding_patch():
    """设置UTF-8编码修补，仅在Windows上生效"""
    import platform

    if platform.system() == 'Windows':
        import builtins

        # 保存原始的open函数
        _original_open = builtins.open

        def patched_open(
            file, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None
        ):
            """
            修补过的open函数，默认对SQL文件使用UTF-8编码
            仅在Windows系统上生效，解决alembic_dddl读取SQL文件的编码问题
            """
            # 如果没有指定编码且是文本模式
            if encoding is None and ('b' not in mode):
                # 对SQL文件使用UTF-8
                if isinstance(file, str):
                    if file.endswith('.sql'):
                        encoding = 'utf-8'

            return _original_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

        # 替换内置的open函数
        builtins.open = patched_open
        print('Applied UTF-8 encoding patch for Windows')


# 应用编码修补
setup_encoding_patch()


import asyncio
from logging.config import fileConfig

from alembic import context
from alembic_dddl import register_ddl
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.models.base_model import Base, TableModel, ViewModel
from app.support.modules_helper import get_classes_inheriting_from_base, import_all_models
from config.database import settings as db_settings

import_all_models('app/models')

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# 设置sqlalchemy.url
config.set_main_option('sqlalchemy.url', db_settings.SQLALCHEMY_DATABASE_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


# ---------------------------------------------------------------
# 获取util实体

util_entities: list = Base.get_init_sql_alembic_ddls()
models_temp: list[Base] = []

# 获取所有继承自ViewModel的类
models_dict = get_classes_inheriting_from_base('app/models', ViewModel, exclude_filenames=['base_model.py'])
# 平铺类型
for module, classes in models_dict.items():
    models_temp.extend(classes.values())  # 把每个模块中的类添加到数组中
# 调用类方法，获取util实体
for model in models_temp:
    util_entities += model.get_ext_alembic_ddls()

# 获取所有继承自TableModel的类
models_dict = get_classes_inheriting_from_base('app/models', TableModel, exclude_filenames=['base_model.py'])
# 平铺类型
for module, classes in models_dict.items():
    models_temp.extend(classes.values())  # 把每个模块中的类添加到数组中
# 调用类方法，获取util实体
for model in models_temp:
    util_entities += model.get_ext_alembic_ddls()

register_ddl(util_entities)

# ---------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option('sqlalchemy.url')
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        compare_server_default=True,  # Added to detect server_default changes
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_server_default=True,  # Added to detect server_default changes
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix='sqlalchemy.', poolclass=pool.NullPool
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
