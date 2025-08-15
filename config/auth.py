from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    JWT_TTL: int = 60 * 24 * 7  # 7 天
    JWT_ISSUER: str = 'fastapi'
    JWT_AUDIENCE: str = 'fastapi'
    JWT_SECRET_KEY: str = 'fastapi123456'
    JWT_ALGORITHM: str = 'HS256'

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',  # 忽略额外的输入
    )


settings = Settings()
