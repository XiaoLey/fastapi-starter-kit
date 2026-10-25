from pydantic import Field

from app.schemas.base import BaseSc


class BoolSc(BaseSc):
    success: bool = True


class ValidationDetailSc(BaseSc):
    loc: list[str | int]
    type: str


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
