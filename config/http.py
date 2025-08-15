from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    USER_AGENT: str = ''

    model_config = SettingsConfigDict(
        env_prefix='HTTP_',
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',  # 忽略额外的输入
    )


settings = Settings()
