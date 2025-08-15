from pydantic_settings import BaseSettings, SettingsConfigDict

from config.config import settings as app_settings


class Settings(BaseSettings):
    POSTGRES_HOST: str = 'localhost'
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = 'fastapi'
    POSTGRES_USER: str = 'postgres'
    POSTGRES_PASSWORD: str = 'fastapi123456'

    POSTGRESQL_SCRIPTS_DIR: str = f'{app_settings.BASE_PATH}/database/postgresql'  # PostgreSQL脚本目录

    @property
    def SQLALCHEMY_DATABASE_URL(self):
        return f'postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}'

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',  # 忽略额外的输入
    )


class RedisSettings(BaseSettings):
    REDIS_HOST: str = 'localhost'
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = 'fastapi123456'

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',  # 忽略额外的输入
    )


settings = Settings()
redis_settings = RedisSettings()
