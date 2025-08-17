import logging

from fastapi import Depends, FastAPI

from app.http.deps import firewall_deps
from app.providers import (
    app_provider,
    exception_provider,
    logging_provider,
    middleware_provider,
    openapi_provider,
    route_provider,
)
from app.providers.lifespan_provider import lifespan
from config.config import settings


def create_app() -> FastAPI:
    base_kwargs = {
        'debug': settings.DEBUG,
        'title': settings.NAME,
        'version': settings.VERSION,
        'lifespan': lifespan,
        'dependencies': [Depends(firewall_deps.verify_ip_banned)],
    }

    if settings.DEBUG:
        app = FastAPI(**base_kwargs)
    else:
        # 生产环境不启用文档
        app = FastAPI(
            **base_kwargs, docs_url=None, redoc_url=None, openapi_url=None, swagger_ui_oauth2_redirect_url=None
        )

    register(app, logging_provider)
    register(app, app_provider)
    register(app, exception_provider)
    register(app, middleware_provider)
    register(app, openapi_provider)

    boot(app, route_provider)

    return app


def register(app, provider):
    provider.register(app)
    logging.info(provider.__name__ + ' registered')


def boot(app, provider):
    provider.boot(app)
    logging.info(provider.__name__ + ' booted')
