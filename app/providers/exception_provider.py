from http import HTTPStatus

from fastapi import FastAPI, WebSocket
from fastapi.exceptions import RequestValidationError, ResponseValidationError, WebSocketRequestValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse, Response

from app.exceptions import ApiError
from app.providers.logging_provider import log_failure
from app.schemas.common import ErrorSc, ValidationDetailSc


def error_response(error: ApiError, *, detail: list[ValidationDetailSc] | None = None) -> JSONResponse:
    body = ErrorSc(code=error.code, message=error.message, detail=detail)
    return JSONResponse(body.model_dump(exclude_none=True), status_code=error.status_code, headers=error.headers)


def register(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def handle_http(connection: HTTPConnection, exc: HTTPException) -> Response:
        if connection.scope['type'] == 'websocket':
            raise exc
        if isinstance(exc, ApiError):
            return error_response(exc)
        if exc.status_code == 401:
            headers = dict(exc.headers) if exc.headers else {}
            if not any(key.lower() == 'www-authenticate' for key in headers):
                headers['WWW-Authenticate'] = 'Bearer'
            return error_response(ApiError(401, 'AUTHENTICATION_ERROR', '身份验证失败', headers=headers))

        # 普通HTTPException也保留协议头，但不透传任意detail内容
        message = HTTPStatus(exc.status_code).phrase if exc.status_code in HTTPStatus else 'HTTP error'
        return error_response(
            ApiError(exc.status_code, 'HTTP_ERROR', message, headers=dict(exc.headers) if exc.headers else None)
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(connection: HTTPConnection, exc: RequestValidationError) -> Response:
        details = [ValidationDetailSc.from_error(error) for error in exc.errors()]
        return error_response(ApiError(422, 'VALIDATION_ERROR', '输入校验失败'), detail=details)

    @app.exception_handler(WebSocketRequestValidationError)
    async def handle_ws_validation(connection: WebSocket, exc: WebSocketRequestValidationError) -> None:
        # 外层ASGI边界掌握真实状态，不能在这里用新建的WebSocket判断已accept
        raise exc

    @app.exception_handler(ValidationError)
    @app.exception_handler(ResponseValidationError)
    async def handle_internal_validation(connection: HTTPConnection, exc: Exception) -> Response:
        if connection.scope['type'] == 'websocket':
            raise exc
        log_failure(exc)
        return error_response(ApiError(500, 'UNKNOWN_ERROR', '内部服务错误'))
