from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

NumericDate = StrictInt | Annotated[StrictFloat, Field(allow_inf_nan=False)]


class JWTSc(BaseModel):
    """验签后的必需声明；缺失字段不能由默认值补齐"""

    model_config = ConfigDict(extra='allow')

    iss: str = Field(min_length=1)
    aud: str = Field(min_length=1)
    sub: UUID
    exp: NumericDate
    nbf: NumericDate
    iat: NumericDate
    jti: str = Field(min_length=1)
