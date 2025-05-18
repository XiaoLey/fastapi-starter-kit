from typing import Optional

from pydantic import Field

from app.schemas.base import BaseSc


class TokenSc(BaseSc):
    """
    令牌
    """
    token_type: str = Field(description='令牌类型', default="bearer")
    expires_in: int = Field(description="过期时间（秒）")
    access_token: str = Field(description="令牌")


class TokenStatusSc(BaseSc):
    """
    令牌状态
    """
    success: bool = Field(description="令牌状态", default=True)
    message: Optional[str] = Field(None, description="令牌状态描述", examples=['Invalid token'])
