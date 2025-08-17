import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """验证配置"""

    USERNAME_MIN_LENGTH: int = 4
    USERNAME_MAX_LENGTH: int = 16
    USERNAME_PATTERN: str | re.Pattern = re.compile(r'^[a-zA-Z0-9_]+$')

    model_config = SettingsConfigDict(
        env_prefix='VERIFY_',
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',  # 忽略额外的输入
    )

    @field_validator('USERNAME_PATTERN', mode='before')
    @classmethod
    def validate_username_pattern(cls, v: str | re.Pattern):
        """将字符串模式转换为正则表达式对象"""
        if isinstance(v, str):
            return re.compile(v)
        return v


settings = Settings()
