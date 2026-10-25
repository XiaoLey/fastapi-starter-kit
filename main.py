import uvicorn

from app.providers.logging_provider import initialize
from config.settings import load_settings


def main() -> None:
    settings = load_settings()
    initialize(settings)

    # 显式覆盖服务器默认信任，不能由外部FORWARDED_ALLOW_IPS意外扩权
    uvicorn.run(
        'api_app:app',
        host=settings.APP_SERVER_HOST,
        port=settings.APP_SERVER_PORT,
        reload=settings.APP_DEBUG,
        workers=1 if settings.APP_DEBUG else settings.APP_WORKERS,
        proxy_headers=bool(settings.APP_TRUSTED_PROXY_IPS),
        forwarded_allow_ips=settings.APP_TRUSTED_PROXY_IPS,
        log_config=None,
        log_level={'SUCCESS': 'info'}.get(settings.LOG_LEVEL, settings.LOG_LEVEL.lower()),
        timeout_keep_alive=120,
    )


if __name__ == '__main__':
    main()
