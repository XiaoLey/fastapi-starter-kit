"""仅在认证模块请求相应能力时校验的配置"""

from pydantic import BaseModel, Field, SecretStr


class JwtSettings(BaseModel):
    """已启用的本地 token 配置"""

    JWT_SECRET_KEY: SecretStr
    JWT_TTL: int = Field(ge=1)
    JWT_ISSUER: str = Field(min_length=1)
    JWT_AUDIENCE: str = Field(min_length=1)
    REDIS_KEY_PREFIX: str


class CodeSettings(BaseModel):
    """已启用的验证码配置"""

    AUTH_CODE_SECRET_KEY: SecretStr
    AUTH_CODE_TTL_SECONDS: int = Field(ge=1)
    AUTH_CODE_MAX_ATTEMPTS: int = Field(ge=1)
    AUTH_CODE_SEND_INTERVAL_SECONDS: int = Field(ge=1)
    REDIS_KEY_PREFIX: str
