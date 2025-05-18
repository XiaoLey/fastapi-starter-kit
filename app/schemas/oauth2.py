from typing import Optional

from pydantic import Field

from app.schemas.base import BaseSc


class OAuth2PasswordSc(BaseSc):
    """
    OAuth2 密码登录请求
    """
    grant_type: str = Field("password", description="授权类型", pattern="^password$", example="password")
    username: str = Field(description="用户名", example="admin")
    password: str = Field(description="密码", example="123456")
    scope: str = Field('', description="授权范围（目前没用上）")
    client_id: Optional[str] = Field(None, description="客户端ID（目前我也不知道这个是干啥的）")
    client_secret: Optional[str] = Field(None, description="客户端密钥（目前我也不知道这个是干啥的）")


class OAuth2CellphoneSc(BaseSc):
    """
    OAuth2 手机号+验证码登录请求
    """
    grant_type: str = Field("cellphone", description="授权类型", pattern="^cellphone$", example="cellphone")
    cellphone: str = Field(description="手机号", example="12345678901")
    verification_code: str = Field(description="验证码", example="123456")
    scope: str = Field('', description="授权范围（目前没用上）")
    client_id: Optional[str] = Field(None, description="客户端ID（目前我也不知道这个是干啥的）")
    client_secret: Optional[str] = Field(None, description="客户端密钥（目前我也不知道这个是干啥的）")
