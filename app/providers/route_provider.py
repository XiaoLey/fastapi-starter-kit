from collections.abc import Sequence

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import iter_route_contexts
from starlette.routing import Route, WebSocketRoute

from app.http import api, health
from app.http.deps.firewall_deps import verify_app_limit, verify_ip_banned
from app.schemas.common import ErrorSc
from app.services.auth.local_auth_service import LocalAuthModule
from app.services.auth.modules import AuthModule
from config.settings import Settings


def boot(app: FastAPI, settings: Settings, modules: Sequence[AuthModule]) -> None:
    """装配普通业务和已选认证，拒绝重复的 HTTP 方法/路径及 WS 路径"""
    # 业务入口统一继承封禁和配额，鉴权仍由各接口显式声明
    business = APIRouter(
        dependencies=[Depends(verify_ip_banned), Depends(verify_app_limit)],
        responses={status: {'model': ErrorSc} for status in (401, 403, 409, 422, 429, 500, 503)},
    )
    business.include_router(api.router)
    for module in modules:
        business.include_router(module.router)

    # 内置注册按实际能力组合一次，不从模块名称推断身份种类
    if any(isinstance(module, LocalAuthModule) for module in modules):
        from app.http.auth_methods.registration import build_router as build_registration_router

        business.include_router(build_registration_router(modules))
    if any(module.uses_local_tokens for module in modules):
        from app.http.auth_core import build_router

        business.include_router(build_router())

    # 健康探针不继承业务的基础设施依赖
    app.include_router(health.router, prefix=settings.APP_API_PREFIX)
    app.include_router(business, prefix=settings.APP_API_PREFIX)

    # 有效上下文包含延迟装配的嵌套路由，不能只检查顶层 routes
    signatures: set[tuple[str, str]] = set()
    for context in iter_route_contexts(app.routes):
        if isinstance(context.original_route, Route):
            methods = context.methods or set()
        elif isinstance(context.original_route, WebSocketRoute):
            methods = {'WEBSOCKET'}
        else:
            continue
        path = context.path
        if path is None:
            continue
        for method in methods:
            signature = (method, path)
            if signature in signatures:
                raise ValueError(f'Duplicate route: {method} {path}')
            signatures.add(signature)
