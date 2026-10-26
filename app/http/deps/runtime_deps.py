from typing import cast

from starlette.requests import HTTPConnection

from app.providers.lifespan_provider import Resources
from config.auth import JwtSettings
from config.settings import Settings


def get_settings(connection: HTTPConnection) -> Settings:
    return cast(Settings, connection.app.state.settings)


def get_jwt_settings(connection: HTTPConnection) -> JwtSettings:
    """取得当前应用启用的本地token配置，未启用时拒绝调用"""
    settings = connection.app.state.jwt_settings
    if not isinstance(settings, JwtSettings):
        raise RuntimeError('Local token authentication is not configured')
    return settings


def get_resources(connection: HTTPConnection) -> Resources:
    """取得当前启动周期的资源，应用未启动或退出后拒绝调用"""
    resources = connection.app.state.resources
    if not isinstance(resources, Resources):
        raise RuntimeError('Application lifespan is not running')
    return resources
