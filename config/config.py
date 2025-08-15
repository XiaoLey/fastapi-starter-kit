import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    NAME: str = 'fastapi'
    VERSION: str = '0.1.0'
    DEBUG: bool = False
    WORKERS: int = 1  # 只有生产模式（非DEBUG）才生效

    SERVER_HOST: str = '0.0.0.0'
    SERVER_DOMAIN: str = '127.0.0.1'
    SERVER_PORT: int = 8000
    API_PREFIX: str = '/api'

    BASE_PATH: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    SEMAPHORE: int = 4  # 通用最大并发数

    QPS: int = 10  # 全局QPS（其他局部的无法高于此值）

    class Config:
        env_prefix = 'APP_'
        env_file = '.env'
        env_file_encoding = 'utf-8'
        extra = 'ignore'  # 忽略额外的输入


settings = Settings()
