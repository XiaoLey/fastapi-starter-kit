"""迁移生成与既有DDDL插件的窄兼容边界"""

import hashlib
from collections.abc import Iterable
from importlib.metadata import version

from alembic.operations import MigrateOperation, ops
from alembic.runtime.migration import MigrationContext
from alembic_dddl.dddl import ddl_registry  # pyright: ignore[reportMissingTypeStubs]
from alembic_dddl.src.models import DDL, RevisionedScript  # pyright: ignore[reportMissingTypeStubs]
from alembic_dddl.src.ops import Script, SyncDDLOp  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import Enum

from app.models.base_model import Base, TableModel, ViewModel


def install_ddl_compatibility() -> None:
    """使固定版本的DDDL操作可被alembic check报告，不隐藏真实差异"""
    if version('alembic-dddl') != '0.1.3':
        raise RuntimeError('Recheck DDDL compatibility before changing its version')

    def identity(script: Script) -> str:
        if isinstance(script, DDL):
            return f'{script.name}:{hashlib.sha256(script.sql.encode()).hexdigest()}'
        if isinstance(script, RevisionedScript):
            return f'{script.name}:{script.revision}'
        return hashlib.sha256(script.encode()).hexdigest()

    def diff(self: SyncDDLOp) -> tuple[str, str, str]:
        return 'sync_ddl', identity(self.up_script), identity(self.down_script)

    if SyncDDLOp.to_diff_tuple is MigrateOperation.to_diff_tuple:
        SyncDDLOp.to_diff_tuple = diff


def collect_ddls() -> tuple[list[DDL], set[str]]:
    # 附属 DDL 与实际映射使用同一份登记，表和视图都只收集一次
    entities = Base.get_init_sql_alembic_ddls()
    view_names: set[str] = set()
    for mapper in sorted(Base.registry.mappers, key=lambda item: (item.class_.__module__, item.class_.__qualname__)):
        model = mapper.class_
        if not issubclass(model, (TableModel, ViewModel)):
            continue
        entities.extend(model.get_ext_alembic_ddls())
        if issubclass(model, ViewModel):
            view_names.add(str(model.__tablename__))

    # 同名但不同定义不能被插件静默覆盖
    unique: dict[str, DDL] = {}
    for entity in entities:
        previous = unique.get(entity.name)
        if previous is not None and previous != entity:
            raise ValueError(f'Conflicting DDL identity: {entity.name}')
        unique[entity.name] = entity
    return list(unique.values()), view_names


def register_project_ddls(entities: list[DDL]) -> None:
    # 迁移环境重复执行时替换本项目登记，不积累进程全局残留
    ddl_registry.ddls[:] = entities


def prepare_schema_migration(
    context: MigrationContext, revisions: Iterable[str | None], directives: list[ops.MigrationScript]
) -> None:
    """保证模型附属 DDL 的建删顺序，初始化回退不遗留原生 enum"""
    # 模型附属DDL依赖表；全局扩展和函数先于表创建
    initial_names = {entity.name for entity in Base.get_init_sql_alembic_ddls()}

    def belongs_to_model(script: Script) -> bool:
        return isinstance(script, (DDL, RevisionedScript)) and script.name not in initial_names

    for directive in directives:
        for upgrade in directive.upgrade_ops_list:
            attached = [
                operation
                for operation in upgrade.ops
                if isinstance(operation, SyncDDLOp) and belongs_to_model(operation.up_script)
            ]
            upgrade.ops[:] = [operation for operation in upgrade.ops if operation not in attached] + attached
        for downgrade in directive.downgrade_ops_list:
            attached = [
                operation
                for operation in downgrade.ops
                if isinstance(operation, SyncDDLOp) and belongs_to_model(operation.down_script)
            ]
            downgrade.ops[:] = attached + [operation for operation in downgrade.ops if operation not in attached]

    # PostgreSQL删表不会自动清除其命名enum，只处理初始化拥有的类型
    if any(revisions):
        return
    names: set[str] = set()
    quote = context.dialect.identifier_preparer.quote
    for table in Base.metadata.tables.values():
        for column in table.columns:
            type_ = column.type
            if isinstance(type_, Enum) and type_.native_enum and type_.name:
                name = quote(type_.name)
                if isinstance(type_.schema, str):
                    name = f'{quote(type_.schema)}.{name}'
                names.add(name)

    for directive in directives:
        for downgrade in directive.downgrade_ops_list:
            downgrade.ops.extend(ops.ExecuteSQLOp(f'DROP TYPE IF EXISTS {name}') for name in sorted(names))
