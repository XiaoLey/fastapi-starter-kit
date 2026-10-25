from typing import Literal

from pydantic import Field, SecretStr

from app.schemas.base import BaseSc
from app.schemas.user import Cellphone, VerificationCode


class OAuth2PasswordSc(BaseSc):
    """登录凭据不使用新注册的用户名格式或密码最小长度"""

    grant_type: Literal['password'] = 'password'
    username: str = Field(min_length=1, max_length=255)
    password: SecretStr = Field(min_length=1, max_length=128)


class OAuth2CellphoneSc(BaseSc):
    cellphone: Cellphone
    verification_code: VerificationCode
    grant_type: Literal['cellphone'] = 'cellphone'
    scope: str = ''
    client_id: str | None = None
    client_secret: SecretStr | None = None


class VerificationCodeReqSc(BaseSc):
    cellphone: Cellphone
    purpose: Literal['register', 'login']
