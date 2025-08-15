#
# 令牌管理服务
#
# 提供令牌的创建、验证和吊销功能，管理令牌的生命周期和状态。
#

from datetime import datetime, timedelta, timezone

from app.exceptions.exception import AuthenticationError
from app.models.user import UserModel
from app.providers.database import redis_client
from app.schemas.token import TokenSc
from app.services.auth import jwt_helper
from config.auth import settings
from config.redis_key import settings as redis_key_settings


def create_token_response_from_user(user: UserModel) -> TokenSc:
    """根据用户模型创建令牌响应"""
    expires_delta = timedelta(minutes=settings.JWT_TTL)
    expires_in = int(expires_delta.total_seconds())
    token = jwt_helper.create_access_token(user.id, expires_delta=expires_delta)

    return TokenSc(token_type='bearer', expires_in=expires_in, access_token=token)


async def validate_token(token: str) -> dict:
    """
    验证 token 并返回解码后的数据
    :return: 对 token 进行 jwt 解码后的数据（按需获取）
    """
    value = await redis_client.get(f'{redis_key_settings.VERIFY_GRANT_TOKEN}:{token}')
    if value and value == 'invalid':
        raise AuthenticationError()

    payload = jwt_helper.get_payload_by_token(token)

    return payload


async def cancel_token(token: str):
    """吊销一个 token"""
    payload = await validate_token(token)
    expire_time = payload.get('exp')
    expire_in = int(expire_time - datetime.now(timezone.utc).timestamp())
    await redis_client.setex(name=f'{redis_key_settings.VERIFY_GRANT_TOKEN}:{token}', time=expire_in, value='invalid')
