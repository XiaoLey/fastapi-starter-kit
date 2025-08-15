from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def alter_enum_type(
    table_name: str,
    column_name: str,
    old_enum_name: str,
    new_enum_name: str,
    old_enum_values: list[str],
    new_enum_values: list[str],
    value_mapping: dict[str, str],
    default_value: Union[str, None],
    nullable: bool = False,
) -> None:
    """
    通用函数，用于在 PostgreSQL 中更改 ENUM 类型，并更新已有数据的字段值。

    参数：
    - table_name: 表名
    - column_name: 列名
    - old_enum_name: 旧的 ENUM 类型名
    - new_enum_name: 新的 ENUM 类型名（临时）
    - old_enum_values: 旧的 ENUM 值列表
    - new_enum_values: 新的 ENUM 值列表
    - value_mapping: 旧值到新值的映射
    - default_value: 列的默认值
    - nullable: 列是否可为空
    """

    # Step 1: 创建新的 ENUM 类型
    new_enum_type = postgresql.ENUM(*new_enum_values, name=new_enum_name)
    new_enum_type.create(op.get_bind(), checkfirst=True)

    # Step 2: 移除默认值和非空约束（如果存在）
    op.execute(f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} DROP DEFAULT
    """)
    if not nullable:
        op.execute(f"""
            ALTER TABLE {table_name}
            ALTER COLUMN {column_name} DROP NOT NULL
        """)

    # Step 3: 将列类型临时修改为 TEXT
    op.execute(f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} TYPE TEXT
    """)

    # Step 4: 更新数据以适应新的 ENUM 值
    # 需要确保数据中不存在旧的 ENUM 中未列出的值
    valid_old_values = set(old_enum_values)
    invalid_values_query = f"""
        SELECT DISTINCT {column_name}
        FROM {table_name}
        WHERE {column_name} IS NOT NULL AND {column_name} NOT IN ({', '.join(f"'{v}'" for v in valid_old_values)})
    """
    invalid_values = op.get_bind().execute(sa.text(invalid_values_query)).fetchall()
    if invalid_values:
        raise ValueError(f'发现无效的旧 ENUM 值: {invalid_values}')

    # 更新数据
    if value_mapping:
        when_statements = ' '.join([f"WHEN '{old}' THEN '{new}'" for old, new in value_mapping.items()])
        # 使用 CASE {column_name} WHEN ... THEN ... 的形式
        op.execute(f"""
            UPDATE {table_name}
            SET {column_name} = CASE {column_name} {when_statements} ELSE {column_name} END
            WHERE {column_name} IS NOT NULL
        """)

    # Step 5: 将列类型修改为新的 ENUM 类型
    op.execute(f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} TYPE {new_enum_name}
        USING {column_name}::{new_enum_name}
    """)

    # Step 6: 重新添加默认值和非空约束（如果需要）
    if default_value is not None:
        op.execute(f"""
            ALTER TABLE {table_name}
            ALTER COLUMN {column_name} SET DEFAULT '{default_value}'
        """)
    if not nullable:
        op.execute(f"""
            ALTER TABLE {table_name}
            ALTER COLUMN {column_name} SET NOT NULL
        """)

    # Step 7: 删除旧的 ENUM 类型并重命名新的 ENUM 类型
    op.execute(f'DROP TYPE {old_enum_name}')
    op.execute(f'ALTER TYPE {new_enum_name} RENAME TO {old_enum_name}')


def alter_column_type(
    table_name: str,
    column_name: str,
    old_type: sa.types.TypeEngine,
    new_type: sa.types.TypeEngine,
    value_conversion: Union[str, None] = None,
    default_value: Union[str, None] = None,
    nullable: bool = False,
) -> None:
    """
    通用函数，用于更改普通类型字段的类型，并更新已有数据的字段值。

    参数：
    - table_name: 表名
    - column_name: 列名
    - old_type: 旧的字段类型
    - new_type: 新的字段类型
    - value_conversion: 数据转换的SQL表达式，例如 "CAST({column_name} AS new_type)"
    - default_value: 列的默认值
    - nullable: 列是否可为空
    """

    # Step 1: 移除默认值和非空约束（如果存在）
    op.execute(f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} DROP DEFAULT
    """)
    if not nullable:
        op.execute(f"""
            ALTER TABLE {table_name}
            ALTER COLUMN {column_name} DROP NOT NULL
        """)

    # Step 2: 如果需要，更新数据以适应新的类型
    if value_conversion:
        op.execute(f"""
            UPDATE {table_name}
            SET {column_name} = {value_conversion}
            WHERE {column_name} IS NOT NULL
        """)

    # Step 3: 更改列的类型
    op.execute(f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} TYPE {new_type}
        USING {column_name}::{new_type}
    """)

    # Step 4: 重新添加默认值和非空约束（如果需要）
    if default_value is not None:
        op.execute(f"""
            ALTER TABLE {table_name}
            ALTER COLUMN {column_name} SET DEFAULT '{default_value}'
        """)
    if not nullable:
        op.execute(f"""
            ALTER TABLE {table_name}
            ALTER COLUMN {column_name} SET NOT NULL
        """)
