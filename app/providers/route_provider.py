from fastapi import APIRouter, Depends, FastAPI
from fastapi_limiter.depends import RateLimiter, WebSocketRateLimiter

from app.providers import rate_limiter_provider
from app.support.modules_helper import get_attributes_from_all_modules
from config.config import settings


def boot(app: FastAPI):
    routers_dict = get_attributes_from_all_modules('app/http/api', 'router')
    router_ws_dict = get_attributes_from_all_modules('app/http/api', 'router_ws')

    app_http = APIRouter(
        dependencies=[
            Depends(RateLimiter(times=settings.QPS, seconds=1, callback=rate_limiter_provider.http_app_callback))
        ]
    )
    app_ws = APIRouter(
        dependencies=[
            Depends(
                WebSocketRateLimiter(times=settings.QPS, seconds=1, callback=rate_limiter_provider.http_app_callback)
            )
        ]
    )

    for router in routers_dict.values():
        app_http.include_router(router)
    for router in router_ws_dict.values():
        app_ws.include_router(router)

    # 注册api路由
    app.include_router(app_http, prefix=settings.API_PREFIX)
    app.include_router(app_ws, prefix=settings.API_PREFIX)

    # 打印路由
    if app.debug:
        for route in app_http.routes:
            print({'path': route.path, 'name': route.name, 'methods': route.methods})
        for route in app_ws.routes:
            print({'path': route.path, 'name': route.name, 'methods': ['WebSocket']})
