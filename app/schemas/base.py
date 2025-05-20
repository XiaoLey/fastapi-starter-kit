from pydantic import BaseModel, ConfigDict


class BaseSc(BaseModel):
    model_config = ConfigDict(
        # 参考：https://docs.pydantic.dev/latest/api/config/
        extra="ignore",             # 忽略未知字段
        validate_assignment=True,   # 允许在对象更改时进行数据校验
        from_attributes=True,       # 允许使用类属性填充（而不是只能用字典填充，旧名字叫做 orm_mode）
        populate_by_name=True,       # 允许通过字段名来填充（而不是只能通过别名来填充）
    )


class BaseWithExtrasSc(BaseModel):
    model_config = ConfigDict(
        extra="allow",              # 允许未知字段
        validate_assignment=True,
        from_attributes=True,
        populate_by_name=True,
    )
