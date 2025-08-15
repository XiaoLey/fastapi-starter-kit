#
# 用户管理服务
#
# 封装核心的用户管理业务逻辑，例如创建新用户。
#

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserModel
from app.schemas.user import UserCreateRecvSc
from app.services.auth import hashing
from app.services.auth.validators import verify_cellphone_availability, verify_username_availability


async def create_user(session: AsyncSession, client_ip: str, new_user: UserCreateRecvSc) -> UserModel:
    """创建用户"""
    # 验证用户名
    await verify_username_availability(session, new_user.username)
    # 验证手机号
    await verify_cellphone_availability(session, new_user.cellphone)

    # 设置密码
    password = None
    if new_user.password:
        password = hashing.get_password_hash(new_user.password)

    # 创建用户
    user = await UserModel(
        **new_user.model_dump(exclude=['password'] + [field for field, value in new_user if value is None]),
        password=password,
    ).create(session)

    return user
