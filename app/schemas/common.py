from pydantic import Field

from app.schemas.base import BaseSc


class BoolSc(BaseSc):
    success: bool = Field(description="是否成功", example=True)
