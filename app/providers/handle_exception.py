import datetime
import json
import logging
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from jose import jwt
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.status import (
    HTTP_401_UNAUTHORIZED,
)

from app.exceptions.error_code import ErrorCode
from app.exceptions.exception import (
    DataBrokenError,
    InternalValidationError,
    InvalidTokenError,
    TokenExpiredError,
    ValidationError,
)


def _encode_headers(headers: dict) -> dict:
    encoded_headers = {}
    for k, v in headers.items():
        encoded_key = quote(k)  # URL 编码键
        encoded_value = quote(v)  # URL 编码值
        encoded_headers[encoded_key] = encoded_value
    return encoded_headers


def _handle_exception(request: Request, exc: StarletteHTTPException, code: str, add_info: any = None) -> JSONResponse:
    headers: dict = getattr(exc, "headers", None)

    if headers:
        if 'Access-Control-Expose-Headers' in headers:
            del headers['Access-Control-Expose-Headers']
        headers['Access-Control-Expose-Headers'] = ','.join(headers.keys())

        # 对 headers 进行 URL 编码处理，确保不会有编码错误
        headers = _encode_headers(headers)

    detail: dict = {
        'code': code,
        # 'request_ip': request.scope['client'][0],
        'time_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
        'add_info': add_info,
    }
    # logging.warning({'status_code': exc.status_code, 'detail': detail, 'headers': headers})
    return JSONResponse(
        {"detail": detail},
        status_code=exc.status_code, headers=headers
    )


def register(app: FastAPI):
    @app.exception_handler(json.decoder.JSONDecodeError)
    async def json_decode_error(request: Request, exc: json.decoder.JSONDecodeError):
        logging.error(exc)
        return _handle_exception(request, DataBrokenError(), code=ErrorCode.DATA_BROKEN_ERROR)

    @app.exception_handler(jwt.ExpiredSignatureError)
    async def jwt_expired_exception_handler(request: Request, exc: jwt.ExpiredSignatureError):
        return _handle_exception(request, TokenExpiredError(), code=ErrorCode.TOKEN_EXPIRED_ERROR)

    @app.exception_handler(jwt.JWTError)
    async def jwt_exception_handler(request: Request, exc: jwt.JWTError):
        return _handle_exception(request, InvalidTokenError(), code=ErrorCode.INVALID_TOKEN_ERROR)

    @app.exception_handler(jwt.JWTClaimsError)
    async def jwt_claims_exception_handler(request: Request, exc: jwt.JWTClaimsError):
        return _handle_exception(request, InvalidTokenError(), code=ErrorCode.INVALID_TOKEN_ERROR)

    @app.exception_handler(StarletteHTTPException)
    async def custom_http_exception_handler(request: Request, exc):
        if exc.status_code == HTTP_401_UNAUTHORIZED and exc.detail == "Not authenticated":
            exc.detail = ErrorCode.AUTHENTICATION_ERROR
        return _handle_exception(request, exc, code=exc.detail)

    @app.exception_handler(PydanticValidationError)
    async def pydantic_exception_handler(request: Request, exc):
        try:
            logging.error(exc.json())
        except:
            logging.error(str(exc))
        return _handle_exception(request, InternalValidationError(), code=ErrorCode.INTERNAL_VALIDATION_ERROR)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc):
        details = exc.errors()
        validation_details = []
        for error in details:
            validation_detail = {
                'loc': error['loc'],
                'type': error['type']
            }
            validation_details.append(validation_detail)
        add_info = {'errors': validation_details}
        logging.warning(str(exc))
        return _handle_exception(request, ValidationError(), code=ErrorCode.VALIDATION_ERROR, add_info=add_info)

    @app.exception_handler(ResponseValidationError)
    async def response_validation_exception_handler(request: Request, exc):
        logging.error(str(exc))
        return _handle_exception(request, InternalValidationError(), code=ErrorCode.INTERNAL_VALIDATION_ERROR)
