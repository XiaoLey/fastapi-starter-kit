#
# 框架异常类
#

from copy import deepcopy

from fastapi import HTTPException
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_422_UNPROCESSABLE_ENTITY,
    HTTP_429_TOO_MANY_REQUESTS,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from app.exceptions.error_code import ErrorCode


def exception_decorator(status_code, detail):
    def decorator(cls):
        def init(self, error_message=None, headers=None):
            headers_copy = deepcopy(headers)
            if error_message:
                if not headers_copy:
                    headers_copy = {'Error-Message': error_message}
                else:
                    headers_copy['Error-Message'] = error_message
            super(type(self), self).__init__(status_code=status_code, detail=detail, headers=headers_copy)

        cls.__init__ = init
        return cls

    return decorator


@exception_decorator(HTTP_500_INTERNAL_SERVER_ERROR, ErrorCode.UNKNOWN_ERROR)
class UnknownError(HTTPException):
    """未知错误"""


@exception_decorator(HTTP_500_INTERNAL_SERVER_ERROR, ErrorCode.UNKNOWN_PROTOCOL)
class UnknownProtocol(HTTPException):
    """未知协议"""


@exception_decorator(HTTP_500_INTERNAL_SERVER_ERROR, ErrorCode.DATA_BROKEN_ERROR)
class DataBrokenError(HTTPException):
    """数据损坏"""


@exception_decorator(HTTP_500_INTERNAL_SERVER_ERROR, ErrorCode.INTERNAL_VALIDATION_ERROR)
class InternalValidationError(HTTPException):
    """内部验证错误"""


@exception_decorator(HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.VALIDATION_ERROR)
class ValidationError(HTTPException):
    """验证错误（参数校验错误）"""


@exception_decorator(HTTP_401_UNAUTHORIZED, ErrorCode.AUTHENTICATION_ERROR)
class AuthenticationError(HTTPException):
    """未认证"""


@exception_decorator(HTTP_400_BAD_REQUEST, ErrorCode.INVALID_CSRF_ERROR)
class InvalidCSRFError(HTTPException):
    """非法 CSRF"""


@exception_decorator(HTTP_401_UNAUTHORIZED, ErrorCode.INVALID_TOKEN_ERROR)
class InvalidTokenError(HTTPException):
    """token 错误"""


@exception_decorator(HTTP_401_UNAUTHORIZED, ErrorCode.TOKEN_EXPIRED_ERROR)
class TokenExpiredError(HTTPException):
    """token 过期"""


@exception_decorator(HTTP_404_NOT_FOUND, ErrorCode.INVALID_USER_ERROR)
class InvalidUserError(HTTPException):
    """无效用户"""


@exception_decorator(HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.INVALID_PASSWORD_ERROR)
class InvalidPasswordError(HTTPException):
    """密码不正确"""


@exception_decorator(HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.USERNAME_ALREADY_EXISTS_ERROR)
class UsernameAlreadyExistsError(HTTPException):
    """用户名已存在"""


@exception_decorator(HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.CELLPHONE_ALREADY_EXISTS_ERROR)
class CellphoneAlreadyExistsError(HTTPException):
    """手机号已存在"""


@exception_decorator(HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.INVALID_USERNAME_ERROR)
class InvalidUsernameError(HTTPException):
    """非法用户名"""


@exception_decorator(HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.INVALID_USERNAME_LENGTH_ERROR)
class InvalidUsernameLengthError(HTTPException):
    """非法用户名长度"""


@exception_decorator(HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.INVALID_CELLPHONE_ERROR)
class InvalidCellphoneError(HTTPException):
    """非法手机号"""


@exception_decorator(HTTP_400_BAD_REQUEST, ErrorCode.INVALID_CELLPHONE_CODE_ERROR)
class InvalidCellphoneCodeError(HTTPException):
    """无效手机验证码"""


@exception_decorator(HTTP_404_NOT_FOUND, ErrorCode.USER_NOT_FOUND_ERROR)
class UserNotFoundError(HTTPException):
    """用户不存在"""


@exception_decorator(HTTP_403_FORBIDDEN, ErrorCode.INVALID_FILE_NAME_ERROR)
class InvalidFileNameError(HTTPException):
    """文件名不合法"""


@exception_decorator(HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.USERNAME_EMPTY_ERROR)
class UsernameEmptyError(HTTPException):
    """用户名为空"""


@exception_decorator(HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.CELLPHONE_EMPTY_ERROR)
class CellphoneEmptyError(HTTPException):
    """手机号为空"""


@exception_decorator(HTTP_403_FORBIDDEN, ErrorCode.INSUFFICIENT_PERMISSIONS_ERROR)
class InsufficientPermissionsError(HTTPException):
    """权限不足"""


@exception_decorator(HTTP_429_TOO_MANY_REQUESTS, ErrorCode.TOO_MANY_REQUESTS)
class TooManyRequestsError(HTTPException):
    """请求太频繁"""


@exception_decorator(HTTP_403_FORBIDDEN, ErrorCode.IP_BANNED_ERROR)
class IPBannedError(HTTPException):
    """IP 已被封禁"""
