from fastapi import FastAPI
from fastapi.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send


def register(app: FastAPI):
    class RealIPMiddleware:
        """一个 ASGI 中间件，用于从请求头中获取真实的客户端 IP 地址

        此中间件会检查 `X-Real-IP` 和 `X-Forwarded-For` 头，
        以确定客户端的真实 IP，并更新 ASGI scope 中的 `client` 信息。
        这对于在反向代理后运行的应用程序非常有用。
        """

        def __init__(self, app: ASGIApp):
            """初始化中间件

            Args:
                app: 下一个 ASGI 应用程序
            """
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            """处理传入的请求

            从请求头中提取真实 IP 地址并更新 scope。

            Args:
                scope: ASGI scope
                receive: ASGI receive channel
                send: ASGI send channel
            """
            # 确保是 HTTP 或 WebSocket 请求
            if scope['type'] not in ('http', 'websocket'):
                await self.app(scope, receive, send)
                return

            # 创建一个 HTTPConnection 对象，方便操作 headers
            request = HTTPConnection(scope, receive)

            # 获取 X-Real-IP 和 X-Forwarded-For 头
            x_real_ip = request.headers.get('X-Real-IP')
            x_forwarded_for = request.headers.get('X-Forwarded-For')

            # 获取客户端真实 IP
            client_ip = x_real_ip or x_forwarded_for or request.client.host
            client_ip = client_ip.split(',')[0]

            # 修改 scope 中的 client 信息
            scope['client'] = (client_ip, scope['client'][1])

            # 继续处理请求
            await self.app(scope, receive, send)

    # 注册中间件
    app.add_middleware(RealIPMiddleware)
