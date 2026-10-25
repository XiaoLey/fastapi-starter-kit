from fastapi import APIRouter, Depends, FastAPI

from app.http.deps.firewall_deps import verify_app_limit, verify_ip_banned
from app.schemas.common import ErrorSc
from app.support.modules_helper import import_all_models
from config.settings import Settings


def boot(app: FastAPI, settings: Settings) -> None:
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

    app.include_router(health, prefix=settings.APP_API_PREFIX)
    app.include_router(business, prefix=settings.APP_API_PREFIX)
