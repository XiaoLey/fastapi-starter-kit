"""对外错误及可替换适配器的失败契约"""

from fastapi import HTTPException


class SafeValueError(ValueError):
    """可公开的校验说明，只允许固定文案或已脱敏的错误详情"""


class ApiError(HTTPException):
    """具有稳定错误码的业务失败，不携带底层异常输入"""

    code: str
    message: str

    def __init__(self, status_code: int, code: str, message: str, *, headers: dict[str, str] | None = None) -> None:
        self.code = code
        self.message = message
        super().__init__(status_code, detail={'code': code, 'message': message}, headers=headers)


class AuthenticationError(ApiError):
    """身份缺失、错误或不可用"""

    def __init__(self) -> None:
        super().__init__(401, 'AUTHENTICATION_ERROR', '身份验证失败', headers={'WWW-Authenticate': 'Bearer'})


class InvalidTokenError(ApiError):
    """凭据无效或已吊销"""

    def __init__(self) -> None:
        super().__init__(401, 'INVALID_TOKEN_ERROR', '凭据无效', headers={'WWW-Authenticate': 'Bearer'})


class TokenExpiredError(ApiError):
    """凭据过期"""

    def __init__(self) -> None:
        super().__init__(401, 'TOKEN_EXPIRED_ERROR', '凭据已过期', headers={'WWW-Authenticate': 'Bearer'})


class DependencyUnavailableError(ApiError):
    """所需的基础设施暂不可用"""

    def __init__(self) -> None:
        super().__init__(503, 'DEPENDENCY_UNAVAILABLE', '服务依赖暂不可用')


class UserAlreadyExistsError(ApiError):
    """账号标识已被历史记录占用"""

    def __init__(self) -> None:
        super().__init__(409, 'USER_ALREADY_EXISTS_ERROR', '认证身份已被占用')


class InvalidVerificationCodeError(ApiError):
    """验证码错误、过期或已消费"""

    def __init__(self) -> None:
        super().__init__(422, 'INVALID_VERIFICATION_CODE_ERROR', '验证码无效')


class TooManyRequestsError(ApiError):
    """固定窗口或发送冷却已限制本次请求"""

    def __init__(self, retry_after: int) -> None:
        super().__init__(429, 'TOO_MANY_REQUESTS', '请求过于频繁', headers={'Retry-After': str(max(1, retry_after))})


class InvalidFileNameError(ApiError):
    """路径不符合相对路径边界"""

    def __init__(self) -> None:
        super().__init__(403, 'INVALID_FILE_NAME_ERROR', '文件路径无效')


class SmsSendError(Exception):
    """短信供应商未确认接受；异常内容不得直接返回或记录"""


class EmailSendError(Exception):
    """邮件供应商未确认接受；异常内容不得直接返回或记录"""
