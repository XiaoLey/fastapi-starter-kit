import asyncio
from dataclasses import dataclass

from fastapi.exceptions import WebSocketRequestValidationError
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from starlette.websockets import WebSocketDisconnect

from app.exceptions import ApiError, DependencyUnavailableError
from app.providers.database_provider import is_dependency_failure
from app.providers.exception_provider import error_response
from app.providers.logging_provider import log_failure


@dataclass
class _State:
    accepted: bool = False
    closed: bool = False
    disconnected: bool = False
    response_started: bool = False
    denial_started: bool = False
    denial_complete: bool = False


class ExceptionBoundary:
    """按实际ASGI消息处理未捕获错误，不在已开始响应后重发HTTP"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] not in ('http', 'websocket'):
            await self.app(scope, receive, send)
            return
        state = _State()

        async def tracked_receive() -> Message:
            message = await receive()
            if message['type'] in ('websocket.disconnect', 'http.disconnect'):
                state.disconnected = True
            return message

        async def tracked_send(message: Message) -> None:
            kind = message['type']
            if kind == 'websocket.accept':
                state.accepted = True
            elif kind == 'websocket.close':
                state.closed = True
            elif kind == 'websocket.http.response.start':
                state.denial_started = True
            elif kind == 'websocket.http.response.body' and not message.get('more_body', False):
                state.denial_complete = True
            elif kind == 'http.response.start':
                state.response_started = True
            try:
                await send(message)
            except OSError:
                state.disconnected = True
                raise

        try:
            await self.app(scope, tracked_receive, tracked_send)
        except WebSocketDisconnect:
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # 可预期业务失败不重复记录为内部错误
            if isinstance(exc, ApiError):
                error = exc
            elif isinstance(exc, WebSocketRequestValidationError):
                error = ApiError(422, 'VALIDATION_ERROR', '输入校验失败')
            elif is_dependency_failure(exc):
                error = DependencyUnavailableError()
            else:
                log_failure(exc)
                error = ApiError(500, 'UNKNOWN_ERROR', '内部服务错误')

            if scope['type'] == 'http':
                if not state.response_started and not state.disconnected:
                    await error_response(error)(scope, receive, send)
                return

            # 已关闭或已收到断连时不发送第二个响应
            if state.closed or state.disconnected or state.denial_complete:
                return
            try:
                if state.denial_started:
                    await tracked_send({'type': 'websocket.http.response.body', 'body': b'', 'more_body': False})
                elif state.accepted:
                    code = 1011 if error.status_code >= 500 else 1008
                    if error.status_code == 503:
                        code = 1013
                    await tracked_send({'type': 'websocket.close', 'code': code, 'reason': error.code})
                elif 'websocket.http.response' in scope.get('extensions', {}):
                    await error_response(error)(scope, receive, tracked_send)
                else:
                    await tracked_send({'type': 'websocket.close', 'code': 1008, 'reason': error.code})
            except (OSError, WebSocketDisconnect):
                return
