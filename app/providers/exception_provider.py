import json
import logging
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from jose import jwt
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.status import HTTP_401_UNAUTHORIZED

from app.exceptions import (
    AuthenticationError,
    DataBrokenError,
    InternalValidationError,
    InvalidTokenError,
    TokenExpiredError,
    ValidationError,
)


def register(app: FastAPI):
    @app.exception_handler(json.decoder.JSONDecodeError)
    async def json_decode_error(request: Request, exc: json.decoder.JSONDecodeError):
        logging.error(exc)
        return _handle_exception(request, DataBrokenError())

    @app.exception_handler(jwt.ExpiredSignatureError)
    async def jwt_expired_exception_handler(request: Request, exc: jwt.ExpiredSignatureError):
        return _handle_exception(request, TokenExpiredError())

    @app.exception_handler(jwt.JWTError)
    async def jwt_exception_handler(request: Request, exc: jwt.JWTError):
        return _handle_exception(request, InvalidTokenError())

    @app.exception_handler(jwt.JWTClaimsError)
    async def jwt_claims_exception_handler(request: Request, exc: jwt.JWTClaimsError):
        return _handle_exception(request, InvalidTokenError())

    @app.exception_handler(StarletteHTTPException)
    async def custom_http_exception_handler(request: Request, exc):
        if exc.status_code == HTTP_401_UNAUTHORIZED and exc.detail == 'Not authenticated':
            return _handle_exception(request, AuthenticationError(message='Not authenticated'))
        return _handle_exception(request, exc)

    @app.exception_handler(PydanticValidationError)
    async def pydantic_exception_handler(request: Request, exc):
        try:
            logging.error(exc.json())
        except:
            logging.error(str(exc))
        return _handle_exception(request, InternalValidationError())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc):
        detail = exc.errors()
        validation_details = []
        for error in detail:
            validation_detail = {'loc': error['loc'], 'type': error['type']}
            validation_details.append(validation_detail)
        add_info = {'message': 'Validation failed', 'detail': validation_details}
        logging.warning(str(exc))
        return _handle_exception(request, ValidationError(), add_info=add_info)

    @app.exception_handler(ResponseValidationError)
    async def response_validation_exception_handler(request: Request, exc):
        logging.error(str(exc))
        return _handle_exception(request, InternalValidationError())


def _encode_headers(headers: dict) -> dict:
    """对 headers 的键和值进行 URL 编码，防止出现编码错误"""
    encoded_headers = {}
    for k, v in headers.items():
        encoded_key = quote(k)  # URL 编码键
        encoded_value = quote(v)  # URL 编码值
        encoded_headers[encoded_key] = encoded_value
    return encoded_headers


def _handle_exception(request: Request, exc: StarletteHTTPException, add_info: any = None) -> JSONResponse:
    headers: dict | None = getattr(exc, 'headers', None)

    if headers:
        if 'Access-Control-Expose-Headers' in headers:
            del headers['Access-Control-Expose-Headers']
        headers['Access-Control-Expose-Headers'] = ','.join(headers.keys())
        headers = _encode_headers(headers)

    if add_info:
        if isinstance(exc.detail, dict):
            exc.detail.update(add_info)
        else:
            exc.detail = {'message': exc.detail, **add_info}

    # logging.warning({'status_code': exc.status_code, 'detail': exc.detail, 'headers': headers})
    return JSONResponse(content=exc.detail, status_code=exc.status_code, headers=headers)
