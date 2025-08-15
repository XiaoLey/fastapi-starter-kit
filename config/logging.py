"""
配置参考loguru
"""

import socket

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings

from config.config import settings as app_settings

_hostname = socket.gethostname()


class Settings(BaseSettings):
    LOG_LEVEL: str = 'INFO'
    LOG_PATH: str = app_settings.BASE_PATH + '/storage/logs/[hostname]-fastapi-{time:YYYY-MM-DD}.log'
    LOG_FILE_WITH_HOSTNAME_PREFIX: bool = False
    LOG_RETENTION: str = '14 days'

    @field_validator('LOG_FILE_WITH_HOSTNAME_PREFIX', mode='after')
    @classmethod
    def validate_log_file_with_hostname_prefix(cls, v, values: ValidationInfo):
        if v:
            values.data['LOG_PATH'] = values.data['LOG_PATH'].replace('[hostname]', _hostname)
        else:
            values.data['LOG_PATH'] = values.data['LOG_PATH'].replace('[hostname]', '')

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        extra = 'ignore'  # 忽略额外的输入


settings = Settings()
