"""内置本地账号的身份规则，不是认证核心的类型全集"""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, EmailStr, StringConstraints

LocalKind = Literal['username', 'phone', 'email']
ContactKind = Literal['phone', 'email']


def _reject_phone_username(value: str) -> str:
    if re.fullmatch(r'1[3-9][0-9]{9}', value):
        raise ValueError('Username must not be a phone number')
    return value


Username = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=3, max_length=64, pattern=r'^[A-Za-z0-9_.-]+$'),
    AfterValidator(_reject_phone_username),
]
Phone = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, pattern=r'^1[3-9][0-9]{9}$')]
Email = Annotated[EmailStr, AfterValidator(str.lower)]
VerificationCode = Annotated[str, StringConstraints(strict=True, pattern=r'^[0-9]{6}$')]


def identity_namespace(kind: LocalKind) -> str:
    return f'local/{kind}'
