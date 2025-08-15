from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Redis Key 配置

    主要为统一管理 redis key 的前缀命名
    """

    VERIFY_GRANT_TOKEN: str = 'verify:grant_token'  # 验证授权令牌（用于标记用户登录登出）
    VERIFY_RANDOM_CODE: str = 'verify:random_code'  # 验证码随机码（用于校验验证码）
    IP_BLACK_LIST: str = 'ip:black_list'  # ip黑名单

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',  # 忽略额外的输入
    )


settings = Settings()
