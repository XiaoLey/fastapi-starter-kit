#
# 请求依赖
#

from fastapi import Request, WebSocket
from fastapi.requests import HTTPConnection

from app.exceptions import UnknownProtocol


async def get_request_ip(request_or_ws: HTTPConnection) -> str:
    """获取请求ip"""
    return request_or_ws.client.host


async def get_timezone(request_or_ws: HTTPConnection) -> str:
    """请求头中获取时区"""
    if isinstance(request_or_ws, Request):
        if 'Time-Zone' in request_or_ws.headers:
            return request_or_ws.headers['Time-Zone']
        elif 'X-Time-Zone' in request_or_ws.headers:
            return request_or_ws.headers['X-Time-Zone']
        else:
            return 'Asia/Shanghai'
    elif isinstance(request_or_ws, WebSocket):
        return request_or_ws.query_params.get('time-zone', 'Asia/Shanghai')
    else:
        raise UnknownProtocol()
