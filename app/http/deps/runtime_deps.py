from typing import cast

from starlette.requests import HTTPConnection

from app.providers.lifespan_provider import Resources
from config.settings import Settings


def get_settings(connection: HTTPConnection) -> Settings:
    return cast(Settings, connection.app.state.settings)


def get_resources(connection: HTTPConnection) -> Resources:
    resources = connection.app.state.resources
    if not isinstance(resources, Resources):
        raise RuntimeError('Application lifespan is not running')
    return resources
