import logging
from math import ceil
from typing import Union

from fastapi import Request, Response, WebSocket

from app.exceptions import TooManyRequestsError


async def default_identifier(request: Union[Request, WebSocket]):
    """默认的速率限制标识符生成器

    Args:
        request: FastAPI 的 Request 或 WebSocket 对象

    Returns:
        一个由 IP 地址和请求路径组成的唯一标识符字符串
    """
    ip = request.client.host
    return ip + ':' + request.scope['path']


async def http_default_callback(request: Request, response: Response, pexpire: int):
    """默认的 HTTP 请求超速回调函数

    当请求过于频繁时调用

    Args:
        request: FastAPI 的 Request 对象
        response: FastAPI 的 Response 对象
        pexpire: 剩余的毫秒数

    Raises:
        TooManyRequestsError: 抛出请求过于频繁的异常
    """
    expire = ceil(pexpire / 1000)
    raise TooManyRequestsError(headers={'Retry-After': str(expire)})


async def ws_default_callback(ws: WebSocket, pexpire: int):
    """默认的 WebSocket 请求超速回调函数

    当请求过于频繁时调用

    Args:
        ws: FastAPI 的 WebSocket 对象
        pexpire: 剩余的毫秒数

    Raises:
        TooManyRequestsError: 抛出请求过于频繁的异常
    """
    # 记录日志，有id频繁访问
    ip = ws.scope['client'][0]
    logging.warning(f'{ip} is frequently requesting {ws.scope["path"]}')

    expire = ceil(pexpire / 1000)
    raise TooManyRequestsError(headers={'Retry-After': str(expire)})


async def http_app_callback(request: Request | WebSocket, response: Response, pexpire: int):
    """App 范围的限流回调函数

    此回调将记录日志，并可能在未来用于IP封锁

    Args:
        request: FastAPI 的 Request 或 WebSocket 对象
        response: FastAPI 的 Response 对象
        pexpire: 剩余的毫秒数

    Raises:
        TooManyRequestsError: 总是抛出请求过于频繁的异常（本地回环地址除外）
    """
    # 记录日志，有id频繁访问
    ip = request.scope['client'][0]
    logging.warning(f'{ip} is frequently requesting {request.scope["path"]}')

    # 忽略本地回环
    if ip == '127.0.0.1':
        return

    raise TooManyRequestsError()
