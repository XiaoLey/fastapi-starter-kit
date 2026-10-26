from collections.abc import Sequence

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import iter_route_contexts
from starlette.routing import Route, WebSocketRoute

from app.http.deps.firewall_deps import verify_app_limit, verify_ip_banned
from app.schemas.common import ErrorSc
from app.services.auth.modules import AuthModule
from app.support.modules_helper import import_all_models
from config.settings import Settings


def boot(app: FastAPI, settings: Settings, modules: Sequence[AuthModule]) -> None:
    # 健康路由独立装配，不继承业务基础设施依赖
    business = APIRouter(
        dependencies=[Depends(verify_ip_banned), Depends(verify_app_limit)],
        responses={status: {'model': ErrorSc} for status in (401, 403, 409, 422, 429, 500, 503)},
    )
    health = APIRouter()
    seen: set[int] = set()
    for module in import_all_models('app.http.api', recursive=True):
        target = health if getattr(module, 'health_router', False) is True else business
        for attribute in ('router', 'router_ws'):
            router = getattr(module, attribute, None)
            if router is None:
                continue
            if not isinstance(router, APIRouter):
                raise TypeError(f'{module.__name__}.{attribute} must be APIRouter')
            if id(router) not in seen:
                seen.add(id(router))
                target.include_router(router)

    # 认证只能显式接入，共用组合入口按构造函数去重
    shared: set[int] = set()
    for module in modules:
        business.include_router(module.router)
        if module.shared_router is not None and id(module.shared_router) not in shared:
            shared.add(id(module.shared_router))
            business.include_router(module.shared_router(settings, modules))
    if any(module.uses_local_tokens for module in modules):
        from app.http.auth_core import build_router

        business.include_router(build_router())

    app.include_router(health, prefix=settings.APP_API_PREFIX)
    app.include_router(business, prefix=settings.APP_API_PREFIX)

    # 有效上下文包含延迟装配的嵌套路由，不能只检查顶层routes
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
