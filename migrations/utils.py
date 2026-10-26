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
    default_value: str | None,
    nullable: bool = False,
) -> None:
    """更改枚举列的取值，转换完成后仍使用原类型名称

    Args:
        new_enum_name: 转换期间使用的临时类型名，不得与无关类型冲突
        old_enum_values: 允许的存量非空值集合
        value_mapping: 源值到目标值的映射；未指定的值保持原文
        default_value: 转换后使用的默认字符串值；None表示不设置默认值

    Raises:
        ValueError: 现存非空值不属于允许的源值集合

    表、列、类型名和值均来自可信迁移定义，不接受外部输入。
    """

    # 临时类型承载目标取值，最终仍保留原类型名称
    new_enum_type = postgresql.ENUM(*new_enum_values, name=new_enum_name)
    new_enum_type.create(op.get_bind(), checkfirst=True)

    # 解除约束对中间转换状态的限制
    op.execute(f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} DROP DEFAULT
    """)
    if not nullable:
        op.execute(f"""
            ALTER TABLE {table_name}
            ALTER COLUMN {column_name} DROP NOT NULL
        """)

    # 文本中间态允许映射旧枚举不接受的新值
    op.execute(f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} TYPE TEXT
    """)

    # 源值不在迁移定义内时拒绝继续转换
    valid_old_values = set(old_enum_values)
    invalid_values_query = f"""
        SELECT DISTINCT {column_name}
        FROM {table_name}
        WHERE {column_name} IS NOT NULL AND {column_name} NOT IN ({', '.join(f"'{v}'" for v in valid_old_values)})
    """
    invalid_values = op.get_bind().execute(sa.text(invalid_values_query)).fetchall()
    if invalid_values:
        raise ValueError(f'发现无效的旧 ENUM 值: {invalid_values}')

    # 显式映射存量值，未列出的值保持原样
    if value_mapping:
        when_statements = ' '.join([f"WHEN '{old}' THEN '{new}'" for old, new in value_mapping.items()])
        op.execute(f"""
            UPDATE {table_name}
            SET {column_name} = CASE {column_name} {when_statements} ELSE {column_name} END
            WHERE {column_name} IS NOT NULL
        """)

    # 目标枚举校验并接管转换后的列值
    op.execute(f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} TYPE {new_enum_name}
        USING {column_name}::{new_enum_name}
    """)

    # 恢复目标默认值与非空约束
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

    # 转换完成后恢复调用方使用的原类型名称
    op.execute(f'DROP TYPE {old_enum_name}')
    op.execute(f'ALTER TYPE {new_enum_name} RENAME TO {old_enum_name}')


def alter_column_type(
    table_name: str,
    column_name: str,
    new_type: sa.types.TypeEngine[object],
    value_conversion: str | None = None,
    default_value: str | None = None,
    nullable: bool = False,
) -> None:
    """更改普通列类型并恢复指定的约束

    Args:
        value_conversion: 直接使用的可信SQL表达式，不替换占位符；省略时使用数据库默认转换
        default_value: 转换后使用的默认字符串值；None表示不设置默认值

    表、列名和SQL表达式来自可信迁移定义，不接受外部输入。
    """

    # 解除约束对中间转换状态的限制
    op.execute(f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} DROP DEFAULT
    """)
    if not nullable:
        op.execute(f"""
            ALTER TABLE {table_name}
            ALTER COLUMN {column_name} DROP NOT NULL
        """)

    # 根据显式表达式整理存量值
    if value_conversion:
        op.execute(f"""
            UPDATE {table_name}
            SET {column_name} = {value_conversion}
            WHERE {column_name} IS NOT NULL
        """)

    # 目标类型接管列值
    op.execute(f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} TYPE {new_type}
        USING {column_name}::{new_type}
    """)

    # 恢复目标默认值与非空约束
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
