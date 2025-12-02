#
# 异常类
#

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


class ErrorCode:
    UNKNOWN_ERROR = 'UNKNOWN_ERROR'  # 未知错误

    UNKNOWN_PROTOCOL = 'UNKNOWN_PROTOCOL'  # 未知的协议

    DATA_BROKEN_ERROR = 'DATA_BROKEN_ERROR'  # 数据损坏

    INTERNAL_VALIDATION_ERROR = 'INTERNAL_VALIDATION_ERROR'  # 内部验证错误
    VALIDATION_ERROR = 'VALIDATION_ERROR'  # 验证错误（参数校验错误）

    AUTHENTICATION_ERROR = 'AUTHENTICATION_ERROR'  # 未认证
    AUTHORIZATION_ERROR = 'AUTHORIZATION_ERROR'  # 未授权
    INVALID_CSRF_ERROR = 'INVALID_CSRF_ERROR'  # 非法 CSRF
    INVALID_TOKEN_ERROR = 'INVALID_TOKEN_ERROR'  # token 无效
    TOKEN_EXPIRED_ERROR = 'TOKEN_EXPIRED_ERROR'  # token 过期

    INVALID_USER_ERROR = 'INVALID_USER_ERROR'  # 无效用户
    INVALID_PASSWORD_ERROR = 'INVALID_PASSWORD_ERROR'  # 密码不正确
    INVALID_VERIFICATION_CODE_ERROR = 'INVALID_VERIFICATION_CODE_ERROR'  # 无效验证码

    USERNAME_ALREADY_EXISTS_ERROR = 'USERNAME_ALREADY_EXISTS_ERROR'  # 用户名已存在
    CELLPHONE_ALREADY_EXISTS_ERROR = 'CELLPHONE_ALREADY_EXISTS_ERROR'  # 手机号已存在

    INVALID_CELLPHONE_ERROR = 'INVALID_CELLPHONE_ERROR'  # 非法手机号
    INVALID_CELLPHONE_CODE_ERROR = 'INVALID_CELLPHONE_CODE_ERROR'  # 无效手机验证码

    USER_NOT_FOUND_ERROR = 'USER_NOT_FOUND_ERROR'  # 用户不存在

    INVALID_FILE_NAME_ERROR = 'INVALID_FILE_NAME_ERROR'  # 传入的文件名非法

    USERNAME_EMPTY_ERROR = 'USERNAME_EMPTY_ERROR'  # 用户名为空
    CELLPHONE_EMPTY_ERROR = 'CELLPHONE_EMPTY_ERROR'  # 手机号为空

    TOO_MANY_REQUESTS = 'TOO_MANY_REQUESTS'  # 请求太频繁
    IP_BANNED_ERROR = 'IP_BANNED_ERROR'  # ip封锁

    @classmethod
    def get_error_code_list(cls):
        return [key for key in cls.__dict__.keys() if not key.startswith('__') and not callable(getattr(cls, key))]


def exception_decorator(status_code, error_code: str):
    """异常装饰器"""

    def decorator(cls):
        def init(self, message=None, headers=None):
            detail = {'code': error_code, 'message': message or ''}
            super(type(self), self).__init__(status_code=status_code, detail=detail, headers=headers)

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
    """token 无效"""


@exception_decorator(HTTP_401_UNAUTHORIZED, ErrorCode.TOKEN_EXPIRED_ERROR)
class TokenExpiredError(HTTPException):
    """token 过期"""


@exception_decorator(HTTP_404_NOT_FOUND, ErrorCode.INVALID_USER_ERROR)
class InvalidUserError(HTTPException):
    """无效用户"""


@exception_decorator(HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.INVALID_PASSWORD_ERROR)
class InvalidPasswordError(HTTPException):
    """密码不正确"""


@exception_decorator(HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.INVALID_VERIFICATION_CODE_ERROR)
class InvalidVerificationCodeError(HTTPException):
    """无效验证码"""


@exception_decorator(HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.USERNAME_ALREADY_EXISTS_ERROR)
class UsernameAlreadyExistsError(HTTPException):
    """用户名已存在"""


@exception_decorator(HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.CELLPHONE_ALREADY_EXISTS_ERROR)
class CellphoneAlreadyExistsError(HTTPException):
    """手机号已存在"""


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


@exception_decorator(HTTP_429_TOO_MANY_REQUESTS, ErrorCode.TOO_MANY_REQUESTS)
class TooManyRequestsError(HTTPException):
    """请求太频繁"""


@exception_decorator(HTTP_403_FORBIDDEN, ErrorCode.IP_BANNED_ERROR)
class IPBannedError(HTTPException):
    """IP 已被封禁"""
