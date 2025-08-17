from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.config import settings


def register(app: FastAPI):
    _add_global_middleware(app)


def _add_global_middleware(app: FastAPI):
    """
    注册全局中间件
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*' if settings.DEBUG else f'https://{settings.SERVER_DOMAIN}'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
