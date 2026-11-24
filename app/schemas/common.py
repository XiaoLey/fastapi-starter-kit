from collections.abc import Mapping
from typing import Self, cast

from pydantic import Field

from app.exceptions import SafeValueError
from app.schemas.base import BaseSc


class BoolSc(BaseSc):
    success: bool = True


class ValidationDetailSc(BaseSc):
    loc: list[str | int]
    type: str
    message: str | None = Field(default=None)

    @classmethod
    def from_error(cls, error: Mapping[str, object]) -> Self:
        """将单条 Pydantic 校验错误转换为可公开详情

        Args:
            error: 包含 loc 和 type 的校验错误条目

        Returns:
            字段位置、错误类型及显式标记为安全的文案；无安全说明时文案为 None
        """
        context = error.get('ctx')
        cause = cast(Mapping[str, object], context).get('error') if isinstance(context, Mapping) else None

        return cls.model_validate({
            'loc': error['loc'],
            'type': error['type'],
            'message': str(cause) if isinstance(cause, SafeValueError) else None,
        })


class ErrorSc(BaseSc):
    code: str
    message: str
    detail: list[ValidationDetailSc] | None = Field(default=None)


class LiveSc(BaseSc):
    status: str = 'alive'


class ReadySc(BaseSc):
    status: str
    database: str
    redis: str
