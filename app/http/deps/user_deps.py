#
# 验证依赖
#

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.exceptions import InsufficientPermissionsError
from app.http.deps.auth_deps import get_auth_user
from app.http.deps.database_deps import get_db
from app.models.user import UserModel


async def verify_admin(user: UserModel = Depends(get_auth_user), session: AsyncSession = Depends(get_db)):
    if not await user.is_admin(session):
        raise InsufficientPermissionsError()
