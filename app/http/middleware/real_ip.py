from fastapi import FastAPI
from fastapi.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send


def register(app: FastAPI):
    class RealIPMiddleware:
        def __init__(self, app: ASGIApp):
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            # 确保是 HTTP 或 WebSocket 请求
            if scope['type'] not in ('http', 'websocket'):
                await self.app(scope, receive, send)
                return

            # 创建一个 HTTPConnection 对象，方便操作 headers
            request = HTTPConnection(scope, receive)

            # 修改 scope 中的 client 信息
            client_ip = self.get_real_client_ip(request)
            client_port = self.get_real_client_port(request)
            scope['client'] = (client_ip, client_port)

            # 继续处理请求
            await self.app(scope, receive, send)

        def get_real_client_ip(self, request: HTTPConnection):
            # 检查 X-Real-IP（通常是最可信的）
            x_real_ip = request.headers.get('X-Real-IP')
            if x_real_ip:
                return x_real_ip.strip()

            # 检查 X-Forwarded-For 的第一个IP（最左边通常是真实客户端）
            x_forwarded_for = request.headers.get('X-Forwarded-For')
            if x_forwarded_for:
                first_ip = x_forwarded_for.split(',')[0].strip()
                return first_ip

            # 使用直连IP
            return request.client.host

        def get_real_client_port(self, request: HTTPConnection):
            # 优先检查 X-Real-Port（从nginx传递的真实端口）
            x_real_port = request.headers.get('X-Real-Port')
            if x_real_port:
                try:
                    return int(x_real_port.strip())
                except (ValueError, AttributeError):
                    pass

            # 使用直连端口
            return request.client.port

    # 注册中间件
    app.add_middleware(RealIPMiddleware)
