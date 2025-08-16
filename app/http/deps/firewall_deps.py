from fastapi.requests import HTTPConnection

from app.exceptions import IPBannedError
from app.providers.database_provider import redis_client
from config.redis_key import settings as redis_key_settings


async def verify_ip_banned(request_or_ws: HTTPConnection) -> bool:
    """验证IP是否被封禁"""
    ip = request_or_ws.client.host

    value = await redis_client.hget(redis_key_settings.IP_BLACK_LIST, ip)

    if value:
        raise IPBannedError()
