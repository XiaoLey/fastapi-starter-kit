from fastapi import FastAPI
from fastapi.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send


def register(app: FastAPI):
    class RealIPMiddleware:
        def __init__(self, app: ASGIApp):
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            # 确保是 HTTP 或 WebSocket 请求
            if scope["type"] not in ("http", "websocket"):
                await self.app(scope, receive, send)
                return

            # 创建一个 HTTPConnection 对象，方便操作 headers
            request = HTTPConnection(scope, receive)

            # 获取 X-Real-IP 和 X-Forwarded-For 头
            x_real_ip = request.headers.get("X-Real-IP")
            x_forwarded_for = request.headers.get("X-Forwarded-For")

            # 获取客户端真实 IP
            client_ip = x_real_ip or x_forwarded_for or request.client.host
            client_ip = client_ip.split(",")[0]

            # 修改 scope 中的 client 信息
            scope["client"] = (client_ip, scope["client"][1])

            # 继续处理请求
            await self.app(scope, receive, send)

    # 注册中间件
    app.add_middleware(RealIPMiddleware)
