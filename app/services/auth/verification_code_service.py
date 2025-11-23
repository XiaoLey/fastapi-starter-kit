#
# 验证码服务
#
# 提供验证码的生成、存储和验证功能，支持 Redis 缓存和开发环境超级验证码。
#

from app.exceptions import InvalidVerificationCodeError
from app.providers.database_provider import redis_client
from app.support.string_helper import numeric_random
from config.config import settings
from config.redis_key import settings as redis_key_settings


async def make_code(key, expired=180, length=6) -> str:
    """生成随机码，存储到服务端，返回随机码

    Args:
        key (str): 验证码的键名
        expired (int): 验证码过期时间，单位为秒，默认180秒
        length (int): 验证码长度，默认6位数字

    Returns:
        str: 生成的随机验证码
    """
    code = numeric_random(length)
    await redis_client.setex(_get_redis_key(key), expired, code)
    return code


async def verify_code(key, verification_code, delete_when_passed=True):
    """校验验证码"""
    # 开发环境，可以任意账号使用超级验证码
    super_code = '417938'
    if settings.DEBUG and verification_code == super_code:
        return

    # 校验验证码
    key = _get_redis_key(key)
    code = await redis_client.get(key)
    passed = code and code == verification_code

    if not passed:
        raise InvalidVerificationCodeError()

    if delete_when_passed:
        await redis_client.delete(key)


def _get_redis_key(key):
    """获取 Redis 存储的随机码键名"""
    return f'{redis_key_settings.VERIFY_RANDOM_CODE}:{key}'
