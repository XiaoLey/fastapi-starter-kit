import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import SchemaItem

from app.models.base_model import Base
from app.support.modules_helper import import_all_models
from config.settings import load_settings
from migrations.support import (
    collect_ddls,
    install_ddl_compatibility,
    protect_nullable_downgrade,
    register_project_ddls,
)

config = context.config
import_all_models('app.models', recursive=True)
install_ddl_compatibility()
entities, view_names = collect_ddls()
register_project_ddls(entities)

database_url = load_settings().database_url
config.set_main_option('sqlalchemy.url', database_url.render_as_string(hide_password=False).replace('%', '%%'))
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def configure(connection: Connection | None = None) -> None:
    def include_object(
        obj: SchemaItem, name: str | None, type_: str, reflected: bool, compare_to: SchemaItem | None
    ) -> bool:
        return not (type_ == 'table' and name in view_names)

    context.configure(
        connection=connection,
        url=database_url if connection is None else None,
        target_metadata=Base.metadata,
        literal_binds=connection is None,
        dialect_opts={'paramstyle': 'named'},
        compare_server_default=True,
        include_object=include_object,
        process_revision_directives=protect_nullable_downgrade,
    )


def do_run_migrations(connection: Connection) -> None:
    configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(database_url, poolclass=pool.NullPool, hide_parameters=True)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    configure()
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_async_migrations())
