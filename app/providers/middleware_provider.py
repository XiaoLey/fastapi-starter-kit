from fastapi import FastAPI

from app.http.middleware.errors import ExceptionBoundary
from app.support.modules_helper import get_attributes_from_all_modules


def register(app: FastAPI) -> None:
    app.add_middleware(ExceptionBoundary)
    hooks = get_attributes_from_all_modules('app.http.middleware', 'register')
    for hook in hooks.values():
        if not callable(hook):
            raise TypeError('Middleware register must be callable')
        hook(app)
