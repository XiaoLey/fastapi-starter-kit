"""认证模块的显式装配契约，不发现或导入配置指定的代码"""

from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from fastapi import APIRouter, FastAPI

from config.settings import Settings


@dataclass(frozen=True)
class AuthModule:
    """一个可选认证实现；共享资源每轮仅装配一次"""

    router: APIRouter
    uses_local_tokens: bool = False  #: 接入统一访问凭据、当前用户和吊销能力
    #: 当前应用启动周期的资源上下文，共享回调只运行一次
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None


type AuthFactory = Callable[[Settings], AuthModule]


def resolve_modules(settings: Settings, factories: Mapping[str, AuthFactory]) -> tuple[AuthModule, ...]:
    """只构造选中模块，拒绝无效注册名、未知或重复选择"""
    if any(not name or name.strip() != name for name in factories):
        raise ValueError('Auth module IDs must be nonblank and have no surrounding whitespace')

    # 配置是唯一启用集合，空集合不启动任何认证能力
    selected = settings.AUTH_MODULES
    if len(selected) != len(set(selected)) or any(name not in factories for name in selected):
        raise ValueError('AUTH_MODULES contains duplicate or unknown module IDs')

    return tuple(factories[name](settings) for name in selected)
