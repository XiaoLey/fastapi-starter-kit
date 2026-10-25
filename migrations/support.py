"""迁移生成与既有DDDL插件的窄兼容边界"""

import hashlib
from collections.abc import Iterable
from importlib.metadata import version

from alembic.operations import MigrateOperation, ops
from alembic.runtime.migration import MigrationContext
from alembic_dddl.dddl import ddl_registry  # pyright: ignore[reportMissingTypeStubs]
from alembic_dddl.src.models import DDL, RevisionedScript  # pyright: ignore[reportMissingTypeStubs]
from alembic_dddl.src.ops import Script, SyncDDLOp  # pyright: ignore[reportMissingTypeStubs]

from app.models.base_model import Base, TableModel, ViewModel
from app.support.modules_helper import get_classes_inheriting_from_base

_NULL_GUARD = """
DO $guard$
DECLARE invalid_count bigint;
BEGIN
    SELECT count(*) INTO invalid_count FROM users WHERE cellphone IS NULL;
    IF invalid_count > 0 THEN
        RAISE EXCEPTION 'Cannot downgrade: % users have NULL cellphone; resolve in a maintenance window', invalid_count;
    END IF;
END
$guard$;
"""


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
    # 表和视图分开收集；相同名字但不同定义不能被插件静默覆盖
    entities = Base.get_init_sql_alembic_ddls()
    view_names: set[str] = set()
    seen: set[type[Base]] = set()
    for base in (ViewModel, TableModel):
        for classes in get_classes_inheriting_from_base('app.models', base, ('base_model.py',)).values():
            for model in classes.values():
                if model in seen:
                    continue
                seen.add(model)
                entities.extend(model.get_ext_alembic_ddls())
                if issubclass(model, ViewModel):
                    view_names.add(str(model.__tablename__))

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


def protect_nullable_downgrade(
    context: MigrationContext, revisions: Iterable[str | None], directives: list[ops.MigrationScript]
) -> None:
    def restores_phone_not_null(container: ops.OpContainer) -> bool:
        for operation in container.ops:
            if isinstance(operation, ops.AlterColumnOp):
                if (
                    operation.table_name == 'users'
                    and operation.column_name == 'cellphone'
                    and operation.modify_nullable is False
                ):
                    return True
            elif isinstance(operation, ops.OpContainer) and restores_phone_not_null(operation):
                return True
        return False

    # 保护来自生成源，而非生成后手改revision
    for directive in directives:
        for downgrade in directive.downgrade_ops_list:
            if restores_phone_not_null(downgrade):
                downgrade.ops.insert(0, ops.ExecuteSQLOp(_NULL_GUARD))
