import logging
from math import ceil
from typing import Union

from fastapi import Request, Response, WebSocket

from app.exceptions.exception import TooManyRequestsError


async def default_identifier(request: Union[Request, WebSocket]):
    ip = request.client.host
    return ip + ':' + request.scope['path']


async def http_default_callback(request: Request, response: Response, pexpire: int):
    """
    default callback when too many requests
    :param request:
    :param pexpire: The remaining milliseconds
    :param response:
    :return:
    """
    expire = ceil(pexpire / 1000)
    raise TooManyRequestsError(headers={'Retry-After': str(expire)})


async def ws_default_callback(ws: WebSocket, pexpire: int):
    """
    default callback when too many requests
    :param ws:
    :param pexpire: The remaining milliseconds
    :return:
    """
    # 记录日志，有id频繁访问
    ip = ws.scope['client'][0]
    logging.warning(f'{ip} is frequently requesting {ws.scope["path"]}')

    expire = ceil(pexpire / 1000)
    raise TooManyRequestsError(headers={'Retry-After': str(expire)})


async def http_app_callback(request: Request | WebSocket, response: Response, pexpire: int):
    """
    app 范围的限流（将会记录日志，有id频繁访问，并且对ip进行封锁）
    """
    # 记录日志，有id频繁访问
    ip = request.scope['client'][0]
    logging.warning(f'{ip} is frequently requesting {request.scope["path"]}')

    # 忽略本地回环
    if ip == '127.0.0.1':
        return

    raise TooManyRequestsError()
