from collections.abc import Callable

from fastapi import FastAPI

from app.providers import app_provider, exception_provider, middleware_provider, openapi_provider, route_provider
from app.providers.lifespan_provider import lifespan
from app.services.sms.sms_sender import SmsSender
from config.settings import Settings, load_settings


def create_app(
    settings: Settings | None = None, *, sms_sender_factory: Callable[[], SmsSender] | None = None
) -> FastAPI:
    """组装独立应用，运行资源仅在lifespan内创建"""
    settings = settings if settings is not None else load_settings()
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=False,
        lifespan=lifespan,
        docs_url='/docs' if settings.APP_DEBUG else None,
        redoc_url=None,
        openapi_url='/openapi.json' if settings.APP_DEBUG else None,
    )
    app.state.settings = settings
    app.state.sms_sender_factory = sms_sender_factory
    app.state.resources = None

    # 公共边界先于路由组装，CORS置于可控错误输出之外
    exception_provider.register(app)
    middleware_provider.register(app)
    app_provider.register(app, settings)
    route_provider.boot(app, settings)
    openapi_provider.register(app, settings)
    return app
