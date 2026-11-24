from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserModel
from app.schemas.user import UserProfileSc


async def create_user(session: AsyncSession, profile: UserProfileSc) -> UserModel:
    """在当前事务内写入普通用户，提交由调用方负责"""
    user = UserModel(nickname=profile.nickname, gender=profile.gender)
    session.add(user)
    await session.flush()
    return user
