#
# CSRF 防护辅助工具
#
# 提供 CSRF 令牌的生成和验证功能，防止跨站请求伪造攻击。
#

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.exceptions import InvalidCSRFError


def generate_csrf_token(secret: str, user_id: str):
    """生成 CSRF 令牌

    Args:
        secret (str): 用于签名的密钥
        user_id (str): 要编码到令牌中的用户 ID

    Returns:
        str: 生成的 CSRF 令牌。
    """
    serializer = URLSafeTimedSerializer(secret)
    return serializer.dumps(user_id, salt=secret)


def validate_csrf_token(secret: str, token: str, user_id: str, max_age: int):
    """验证 CSRF 令牌

    Args:
        secret (str): 用于签名的密钥
        token (str): 要验证的 CSRF 令牌
        user_id (str): 期望在令牌中找到的用户 ID
        max_age (int): 令牌的最大有效时间（秒）

    Raises:
        InvalidCSRFError: 如果令牌无效、签名错误、过期或用户 ID 不匹配
    """
    serializer = URLSafeTimedSerializer(secret)
    try:
        decoded_id = serializer.loads(token, salt=secret, max_age=max_age)
    except BadSignature:
        raise InvalidCSRFError()
    if decoded_id != user_id:
        raise InvalidCSRFError()
