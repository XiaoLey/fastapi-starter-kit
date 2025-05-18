import logging

from fastapi import Depends, FastAPI

import app.http.deps as deps
from app.providers import (
    app_provider,
    handle_exception,
    logging_provider,
    middleware_provider,
    route_provider,
)
from app.providers.app_lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=lifespan,
        dependencies=[
            Depends(deps.verify_ip_banned),
        ],
    )

    register(app, logging_provider)
    register(app, app_provider)
    register(app, handle_exception)
    register(app, middleware_provider)

    boot(app, route_provider)

    return app


def register(app, provider):
    provider.register(app)
    logging.info(provider.__name__ + ' registered')


def boot(app, provider):
    provider.boot(app)
    logging.info(provider.__name__ + ' booted')
