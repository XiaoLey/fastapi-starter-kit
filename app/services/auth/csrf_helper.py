#
# CSRF 辅助工具
#

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.exceptions.exception import InvalidCSRFError


def generate_csrf_token(secret: str, user_id: str):
    serializer = URLSafeTimedSerializer(secret)
    return serializer.dumps(user_id, salt=secret)


def validate_csrf_token(secret: str, token: str, user_id: str, max_age: int):
    serializer = URLSafeTimedSerializer(secret)
    try:
        decoded_id = serializer.loads(token, salt=secret, max_age=max_age)
    except BadSignature:
        raise InvalidCSRFError()
    if decoded_id != user_id:
        raise InvalidCSRFError()
