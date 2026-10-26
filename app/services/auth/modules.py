"""认证模块的显式装配契约，不发现或导入配置指定的代码"""

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from fastapi import APIRouter, FastAPI

from config.settings import Settings


@dataclass(frozen=True)
class AuthModule:
    """一个可选认证实现；共用路由和lifespan按 callable 去重"""

    id: str
    router: APIRouter
    uses_local_tokens: bool = False
    shared_router: Callable[[Settings, Sequence['AuthModule']], APIRouter] | None = None
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None


@dataclass(frozen=True)
class AuthModuleFactory:
    """应用可信代码注册的模块构造器，不创建运行资源"""

    id: str
    build: Callable[[Settings], AuthModule]


def resolve_modules(settings: Settings, factories: Sequence[AuthModuleFactory]) -> tuple[AuthModule, ...]:
    # 注册错误不能被未选择的模块或字典覆盖隐藏
    registry: dict[str, AuthModuleFactory] = {}
    for factory in factories:
        if not factory.id or factory.id.strip() != factory.id or factory.id in registry:
            raise ValueError('Auth module IDs must be nonblank and unique')
        registry[factory.id] = factory

    # 配置是唯一启用集合，空集合不启动任何认证能力
    selected = settings.AUTH_MODULES
    if len(selected) != len(set(selected)) or any(module_id not in registry for module_id in selected):
        raise ValueError('AUTH_MODULES contains duplicate or unknown module IDs')
    modules: list[AuthModule] = []
    for module_id in selected:
        module = registry[module_id].build(settings)
        if module.id != module_id:
            raise ValueError('Auth module ID differs from its registered factory')
        modules.append(module)

    return tuple(modules)
