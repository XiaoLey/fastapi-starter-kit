import datetime
import uuid
from typing import Any, Optional

from pydantic import Field, field_validator

from app.schemas.base import BaseWithExtrasSc


class JWTSc(BaseWithExtrasSc):
    iss: str = Field(..., description="发行者")
    aud: Optional[str] = Field(default=None, description="接收方")
    sub: Optional[str] = Field(default=None, description="主题")
    exp: datetime.datetime = Field(..., description="过期时间")
    nbf: datetime.datetime = Field(default=datetime.now(datetime.timezone.utc), description="在此时间之前无效")
    iat: datetime.datetime = Field(default=datetime.now(datetime.timezone.utc), description="签发时间")
    jti: str = Field(default=str(uuid.uuid4()), description="JWT 的唯一标识符")

    @field_validator('exp', mode='before')
    @classmethod
    def normalize_exp(cls, value: Any):
        """将过期时间转换为 datetime 对象"""
        if isinstance(value, datetime.datetime):
            return value

        if isinstance(value, datetime.timedelta):
            return datetime.datetime.now(datetime.timezone.utc) + value

        return value
