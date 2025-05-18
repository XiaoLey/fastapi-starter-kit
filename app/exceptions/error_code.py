# 错误码

class ErrorCode:
    UNKNOWN_ERROR = 'UNKNOWN_ERROR'                                     # 未知错误

    UNKNOWN_PROTOCOL = 'UNKNOWN_PROTOCOL'                               # 未知的协议

    DATA_BROKEN_ERROR = 'DATA_BROKEN_ERROR'                             # 数据损坏

    INTERNAL_VALIDATION_ERROR = 'INTERNAL_VALIDATION_ERROR'             # 内部验证错误
    VALIDATION_ERROR = 'VALIDATION_ERROR'                               # 验证错误（参数校验错误）

    AUTHENTICATION_ERROR = 'AUTHENTICATION_ERROR'                       # 未认证
    AUTHORIZATION_ERROR = 'AUTHORIZATION_ERROR'                         # 未授权
    INVALID_CSRF_ERROR = 'INVALID_CSRF_ERROR'                           # 非法 CSRF
    INVALID_TOKEN_ERROR = 'INVALID_TOKEN_ERROR'                         # token 错误
    TOKEN_EXPIRED_ERROR = 'TOKEN_EXPIRED_ERROR'                         # token 过期

    INVALID_USER_ERROR = 'INVALID_USER_ERROR'                           # 无效用户
    INVALID_PASSWORD_ERROR = 'INVALID_PASSWORD_ERROR'                   # 密码不正确

    USERNAME_ALREADY_EXISTS_ERROR = 'USERNAME_ALREADY_EXISTS_ERROR'     # 用户名已存在
    EMAIL_ALREADY_EXISTS_ERROR = 'EMAIL_ALREADY_EXISTS_ERROR'           # 邮箱已存在
    CELLPHONE_ALREADY_EXISTS_ERROR = 'CELLPHONE_ALREADY_EXISTS_ERROR'   # 手机号已存在

    INVALID_USERNAME_ERROR = 'INVALID_USERNAME_ERROR'                   # 非法用户名
    INVALID_USERNAME_LENGTH_ERROR: str = 'INVALID_USERNAME_LENGTH_ERROR'  # 非法用户名长度
    INVALID_CELLPHONE_ERROR = 'INVALID_CELLPHONE_ERROR'                 # 非法手机号
    INVALID_EMAIL_ERROR = 'INVALID_EMAIL_ERROR'                         # 非法邮箱
    INVALID_EMAIL_CODE_ERROR = 'INVALID_EMAIL_CODE_ERROR'               # 无效邮箱验证码
    INVALID_CELLPHONE_CODE_ERROR = 'INVALID_CELLPHONE_CODE_ERROR'       # 无效手机验证码

    USER_NOT_FOUND_ERROR = 'USER_NOT_FOUND_ERROR'                       # 用户不存在

    INVALID_FILE_NAME_ERROR = 'INVALID_FILE_NAME_ERROR'                 # 传入的文件名非法

    USERNAME_EMPTY_ERROR = 'USERNAME_EMPTY_ERROR'                       # 用户名为空
    EMAIL_EMPTY_ERROR = 'EMAIL_EMPTY_ERROR'                             # 邮箱为空
    CELLPHONE_EMPTY_ERROR = 'CELLPHONE_EMPTY_ERROR'                     # 手机号为空

    INSUFFICIENT_PERMISSIONS_ERROR = 'INSUFFICIENT_PERMISSIONS_ERROR'   # 权限不足

    TOO_MANY_REQUESTS = 'TOO_MANY_REQUESTS'                             # 请求太频繁
    IP_BANNED_ERROR = 'IP_BANNED_ERROR'                                 # ip封锁

    @classmethod
    def get_error_code_list(cls):
        return [key for key in cls.__dict__.keys() if not key.startswith('__') and not callable(getattr(cls, key))]
