from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserModel
from app.types import GENDER_TYPE


async def create_user(
    session: AsyncSession,
    *,
    username: str,
    nickname: str,
    gender: GENDER_TYPE,
    password_hash: str | None = None,
    cellphone: str | None = None,
) -> UserModel:
    """写入普通账号并flush，完整业务事务由调用方提交"""
    user = UserModel(username=username, nickname=nickname, gender=gender, password=password_hash, cellphone=cellphone)
    session.add(user)
    await session.flush()
    return user
