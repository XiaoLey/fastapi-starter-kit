from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.http.middleware.errors import ExceptionBoundary
from config.settings import Settings


def register(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(ExceptionBoundary)

    # 最后添加的用户中间件在外层，为可控错误响应附加 CORS 头
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.APP_CORS_ORIGINS,
        allow_credentials=settings.APP_CORS_ALLOW_CREDENTIALS,
        allow_methods=['*'],
        allow_headers=['*'],
        expose_headers=['WWW-Authenticate', 'Retry-After', 'Allow'],
    )
