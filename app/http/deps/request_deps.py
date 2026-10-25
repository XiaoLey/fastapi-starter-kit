from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from starlette.requests import HTTPConnection

from app.exceptions import ApiError


def get_request_ip(connection: HTTPConnection) -> str:
    """仅使用服务器已规范化的连接来源"""
    if connection.client is None:
        raise ApiError(503, 'CLIENT_ADDRESS_UNAVAILABLE', '连接来源不可用')
    return connection.client.host


def get_timezone(connection: HTTPConnection) -> str:
    """返回有效IANA时区，默认Asia/Shanghai"""
    if connection.scope['type'] == 'websocket':
        zone = connection.query_params.get('time-zone', 'Asia/Shanghai')
    else:
        zone = connection.headers.get('Time-Zone', connection.headers.get('X-Time-Zone', 'Asia/Shanghai'))
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ApiError(422, 'VALIDATION_ERROR', '时区无效') from None
    return zone
