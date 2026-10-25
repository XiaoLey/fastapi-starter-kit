import re
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, SecretStr, StringConstraints, field_validator, model_validator

from app.schemas.base import BaseSc
from app.types import GENDER_TYPE, USER_STATE_TYPE

Cellphone = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, pattern=r'^1[3-9][0-9]{9}$')]
VerificationCode = Annotated[str, StringConstraints(strict=True, pattern=r'^[0-9]{6}$')]


class UserCreateReqSc(BaseSc):
    """公开注册资料；手机号与验证码须同时提供或省略"""

    username: str = Field(min_length=3, max_length=64, pattern=r'^[A-Za-z0-9_.-]+$')
    password: SecretStr = Field(min_length=12, max_length=128)
    nickname: str = Field(min_length=1, max_length=255)
    gender: GENDER_TYPE
    cellphone: Cellphone | None = Field(default=None)
    cellphone_verification_code: VerificationCode | None = Field(default=None)

    @field_validator('username', mode='before')
    @classmethod
    def trim_username(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator('username')
    @classmethod
    def reject_phone_username(cls, value: str) -> str:
        if re.fullmatch(r'1[3-9][0-9]{9}', value):
            raise ValueError('Username must not be a cellphone number')
        return value

    @model_validator(mode='after')
    def require_phone_pair(self) -> Self:
        if (self.cellphone is None) != (self.cellphone_verification_code is None):
            raise ValueError('Cellphone and verification code must be provided together')
        return self


class UserSc(BaseSc):
    """当前账号可读取的资料，不包含认证秘密"""

    id: UUID
    username: str
    nickname: str
    gender: GENDER_TYPE
    avatar: str
    cellphone: str | None
    state: USER_STATE_TYPE
    is_admin: bool
