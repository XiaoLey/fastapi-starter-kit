-- 函数
-- 创建枚举类型（如果不存在）
-- 参数：枚举类型名称，枚举值...
-- 示例：create_enum_type_if_not_exists('gender', 'male', 'female', 'unknown');
CREATE OR REPLACE FUNCTION create_enum_type_if_not_exists(type_name text, variadic enum_values text[])
RETURNS void AS $$
DECLARE
    enum_values_str text;
    quoted_values text[];
    type_exists boolean;
BEGIN
    -- 对每个枚举值进行引用
    quoted_values := ARRAY(SELECT quote_literal(value) FROM unnest(enum_values) AS value);

    -- 将引用后的枚举值数组转换为字符串
    enum_values_str := array_to_string(quoted_values, ',');

    -- 检查类型是否存在
    SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = type_name) INTO type_exists;

    -- 如果类型不存在，则创建类型
    IF NOT type_exists THEN
        EXECUTE format('CREATE TYPE %I AS ENUM (%s)', type_name, enum_values_str);
    END IF;
END;
$$ LANGUAGE plpgsql;