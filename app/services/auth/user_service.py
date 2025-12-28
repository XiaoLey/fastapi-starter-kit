#
# 用户管理服务
#
# 封装核心的用户管理业务逻辑，例如创建新用户。
#

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserModel
from app.schemas.user import UserCreateReqSc
from app.support import password_helper


async def create_user(session: AsyncSession, client_ip: str, new_user: UserCreateReqSc) -> UserModel:
    """创建用户"""
    if password := new_user.password:
        password = password_helper.get_password_hash(password)

    # 创建用户
    user = UserModel(
        **new_user.model_dump(exclude=['password'] + [field for field, value in new_user if value is None]),
        password=password,
    )

    session.add(user)
    await session.flush()

    return user
