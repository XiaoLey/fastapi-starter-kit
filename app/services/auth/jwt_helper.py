#
# JWT 辅助工具
#

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Union

from jose import jwt

from config.auth import settings


def create_access_token(
    subject: Union[str, Any], expires_delta: timedelta = None, additional_claims: dict[str, Any] = None
) -> str:
    """
    创建一个 JWT 访问令牌。

    :param subject: 主题或用户的标识符。
    :param expires_delta: 令牌的有效期 (exp)
    :param additional_claims: 额外的私有声明。
    :return: 编码的 JWT 令牌。
    """
    # 设置过期时间
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_TTL)

    # 设置公共声明
    to_encode = {
        'iss': settings.JWT_ISSUER,  # 发行者
        'aud': settings.JWT_AUDIENCE,  # 接收方
        'sub': str(subject),  # 主题
        'exp': expire,  # 过期时间
        'nbf': datetime.now(timezone.utc),  # 在此时间之前无效
        'iat': datetime.now(timezone.utc),  # 签发时间
        'jti': str(uuid.uuid4()),  # JWT 的唯一标识符
    }

    # 添加额外的私有声明
    if additional_claims:
        to_encode.update(additional_claims)

    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def get_payload_by_token(encoded_jwt):
    """
    解码并返回 JWT 负载。

    :param encoded_jwt: 编码的 JWT 令牌。
    :return: 解码后的负载数据。
    """
    payload = jwt.decode(
        encoded_jwt,
        key=settings.JWT_SECRET_KEY,
        algorithms=settings.JWT_ALGORITHM,
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
    )
    return payload
