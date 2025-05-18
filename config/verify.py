import re

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """ 验证配置 """

    USERNAME_MIN_LENGTH: int = 4
    USERNAME_MAX_LENGTH: int = 16
    USERNAME_PATTERN: str | re.Pattern = re.compile(r"^[a-zA-Z0-9_]+$")

    class Config:
        env_prefix = 'VERIFY_'
        env_file = ".env"
        env_file_encoding = 'utf-8'
        extra = "ignore"  # 忽略额外的输入


settings = Settings()
