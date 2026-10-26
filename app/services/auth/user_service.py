from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserModel
from app.schemas.user import UserProfileSc


async def create_user(session: AsyncSession, profile: UserProfileSc) -> UserModel:
    """创建普通用户并flush，提交由完整业务事务负责"""
    user = UserModel(nickname=profile.nickname, gender=profile.gender)
    session.add(user)
    await session.flush()
    return user
