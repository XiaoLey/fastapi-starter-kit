from app.providers.database import redis_client
from app.support.helper import numeric_random
from config.config import settings
from config.redis_key import settings as redis_key_settings


def _get_redis_key(key):
    return f"{redis_key_settings.VERIFY_RANDOM_CODE}:{key}"


async def make(key, expired=180, length=6) -> str:
    """
    生成随机码，存储到服务端，返回随机码
    """
    code = numeric_random(length)
    await redis_client.setex(_get_redis_key(key), expired, code)
    return code


async def verify(key, verification_code, delete_when_passed=True) -> bool:
    """
    校验验证码
    """
    # 开发环境，可以任意账号使用超级验证码
    super_code = '417938'
    if settings.DEBUG and verification_code == super_code:
        return True

    # 校验验证码
    key = _get_redis_key(key)
    code = await redis_client.get(key)
    passed = code and code == verification_code
    # 若通过验证立即删除
    if passed and delete_when_passed:
        await redis_client.delete(key)
    return passed
