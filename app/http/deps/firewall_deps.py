from collections.abc import Awaitable
from typing import cast

from starlette.requests import HTTPConnection

from app.exceptions import ApiError
from app.http.deps.request_deps import get_request_ip
from app.http.deps.runtime_deps import get_resources, get_settings


async def verify_ip_banned(connection: HTTPConnection) -> None:
    ip = get_request_ip(connection)
    resources, settings = get_resources(connection), get_settings(connection)
    if await cast(Awaitable[str | None], resources.redis_client.hget(f'{settings.REDIS_KEY_PREFIX}:ip:black_list', ip)):
        raise ApiError(403, 'IP_BANNED_ERROR', '连接来源已被禁止')


async def verify_app_limit(connection: HTTPConnection) -> None:
    settings = get_settings(connection)
    scope = 'http' if connection.scope['type'] == 'http' else 'ws:handshake'
    await get_resources(connection).limiter.hit(settings.APP_QPS, 1, scope, get_request_ip(connection))


async def verify_login_limit(connection: HTTPConnection) -> None:
    await get_resources(connection).limiter.hit(5, 60, 'login', get_request_ip(connection))


async def verify_register_limit(connection: HTTPConnection) -> None:
    await get_resources(connection).limiter.hit(3, 60, 'register', get_request_ip(connection))


async def verify_ws_message_limit(connection: HTTPConnection, policy: str, amount: int, seconds: int) -> None:
    """消息处理前显式检查配额，不复用握手次数"""
    await get_resources(connection).limiter.hit(amount, seconds, 'ws:message', policy, get_request_ip(connection))
