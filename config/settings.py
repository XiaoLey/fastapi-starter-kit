"""应用配置契约"""

from pathlib import Path
from typing import Literal, Self

from pydantic import (
    Field,
    IPvAnyAddress,
    IPvAnyNetwork,
    SecretStr,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PLACEHOLDERS = {'fastapi123456', 'changeme', 'change-me', 'replace-me', 'postgres', 'password'}
_PROXY_ADAPTER = TypeAdapter(list[IPvAnyAddress | IPvAnyNetwork])


class Settings(BaseSettings):
    """单个应用的配置；进程环境优先于根目录 dotenv"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / '.env', env_file_encoding='utf-8', extra='ignore', validate_default=True
    )

    APP_NAME: str = 'FastAPI Starter'
    APP_VERSION: str = '0.1.0'
    APP_ENV: Literal['development', 'test', 'production'] = 'development'
    APP_DEBUG: bool = False
    APP_WORKERS: int = Field(default=1, ge=1)
    APP_SERVER_HOST: str = '127.0.0.1'
    APP_SERVER_PORT: int = Field(default=8000, ge=1, le=65535)
    APP_API_PREFIX: str = '/api'
    APP_QPS: int = Field(default=10, ge=1)
    APP_CORS_ORIGINS: list[str] = Field(default_factory=list)
    APP_CORS_ALLOW_CREDENTIALS: bool = False
    APP_TRUSTED_PROXY_IPS: str = ''

    POSTGRES_HOST: str = 'localhost'
    POSTGRES_PORT: int = Field(default=5432, ge=1, le=65535)
    POSTGRES_DB: str = 'fastapi'
    POSTGRES_USER: str = 'postgres'
    POSTGRES_PASSWORD: SecretStr = SecretStr('')
    POSTGRES_POOL_SIZE: int = Field(default=4, ge=1)
    POSTGRES_MAX_OVERFLOW: int = Field(default=4, ge=0)
    POSTGRES_POOL_TIMEOUT: float = Field(default=30, gt=0)
    POSTGRES_POOL_RECYCLE: int = Field(default=1800, gt=0)

    REDIS_HOST: str = 'localhost'
    REDIS_PORT: int = Field(default=6379, ge=1, le=65535)
    REDIS_DB: int = Field(default=0, ge=0)
    REDIS_PASSWORD: SecretStr = SecretStr('')
    REDIS_KEY_PREFIX: str = Field(default='fastapi', min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.:-]+$')

    JWT_SECRET_KEY: SecretStr
    JWT_TTL: int = Field(default=30, ge=1)
    JWT_ISSUER: str = Field(default='fastapi-starter-kit', min_length=1)
    JWT_AUDIENCE: str = Field(default='api', min_length=1)
    SMS_ENABLED: bool = False
    SMS_CODE_SECRET_KEY: SecretStr | None = None
    SMS_CODE_TTL_SECONDS: int = Field(default=300, ge=1)
    SMS_CODE_MAX_ATTEMPTS: int = Field(default=5, ge=1)
    SMS_SEND_INTERVAL_SECONDS: int = Field(default=60, ge=1)

    LOG_LEVEL: Literal['TRACE', 'DEBUG', 'INFO', 'SUCCESS', 'WARNING', 'ERROR', 'CRITICAL'] = 'INFO'
    LOG_PATH: str | None = None
    LOG_FILE_WITH_HOSTNAME_PREFIX: bool = False
    LOG_RETENTION: str = '14 days'

    @field_validator('APP_API_PREFIX')
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith('/') or value.endswith('/'):
            raise ValueError('API prefix must start with / and have no trailing slash')
        return value

    @field_validator('APP_TRUSTED_PROXY_IPS')
    @classmethod
    def validate_proxies(cls, value: str) -> str:
        if not value.strip():
            return ''
        addresses = _PROXY_ADAPTER.validate_python([part.strip() for part in value.split(',')])
        return ','.join(str(address) for address in addresses)

    @field_validator('JWT_SECRET_KEY', 'SMS_CODE_SECRET_KEY')
    @classmethod
    def validate_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        raw = value.get_secret_value()
        if len(raw.encode('utf-8')) < 32 or raw.lower() in _PLACEHOLDERS or raw.lower().startswith('replace-'):
            raise ValueError('A non-placeholder secret of at least 32 bytes is required')
        return value

    @model_validator(mode='after')
    def validate_boundaries(self) -> Self:
        # 浏览器凭据与宽泛来源不能同时启用
        if self.APP_CORS_ALLOW_CREDENTIALS and '*' in self.APP_CORS_ORIGINS:
            raise ValueError('Credentialed CORS requires explicit origins')
        if self.SMS_ENABLED and self.SMS_CODE_SECRET_KEY is None:
            raise ValueError('SMS requires a separate code secret')
        if self.SMS_CODE_SECRET_KEY is not None and self.SMS_CODE_SECRET_KEY == self.JWT_SECRET_KEY:
            raise ValueError('SMS and JWT secrets must differ')

        # 生产环境不能继承演示配置
        if self.APP_ENV == 'production':
            if self.APP_DEBUG or self.REDIS_KEY_PREFIX == 'fastapi':
                raise ValueError('Production requires DEBUG=false and an application-specific Redis prefix')
            for name in ('POSTGRES_PASSWORD', 'REDIS_PASSWORD'):
                secret = self.POSTGRES_PASSWORD if name == 'POSTGRES_PASSWORD' else self.REDIS_PASSWORD
                raw = secret.get_secret_value()
                if (
                    name not in self.model_fields_set
                    or not raw
                    or raw.lower() in _PLACEHOLDERS
                    or raw.lower().startswith('replace-')
                ):
                    raise ValueError('Production requires explicit non-demo dependency credentials')
        return self

    @property
    def database_url(self) -> URL:
        return URL.create(
            'postgresql+asyncpg',
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD.get_secret_value(),
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )


def load_settings() -> Settings:
    """读取配置，错误仅报告字段位置与类型，不输出秘密输入"""
    try:
        return Settings.model_validate({})
    except ValidationError as exc:
        errors = [(error['loc'], error['type']) for error in exc.errors(include_input=False, include_context=False)]
        raise RuntimeError(f'Invalid settings: {errors}') from None
