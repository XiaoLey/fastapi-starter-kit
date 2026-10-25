from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import UserAlreadyExistsError
from app.models.user import UserModel


def unique_field(exc: IntegrityError) -> str | None:
    """只识别模板拥有的用户名/手机号唯一约束"""
    original = exc.orig
    state: object = getattr(original, 'sqlstate', None)
    constraint: object = getattr(original.__cause__ if original is not None else None, 'constraint_name', None)
    if state == '23505':
        if constraint == 'users_username_key':
            return 'username'
        if constraint == 'users_cellphone_key':
            return 'cellphone'
    return None


async def validate_username_availability(session: AsyncSession, username: str, exclude_id: UUID | None = None) -> None:
    query = sa.select(UserModel.id).where(sa.or_(UserModel.username == username, UserModel.cellphone == username))
    if exclude_id is not None:
        query = query.where(UserModel.id != exclude_id)
    if await session.scalar(query.limit(1)) is not None:
        raise UserAlreadyExistsError()


async def validate_cellphone_availability(
    session: AsyncSession, cellphone: str, exclude_id: UUID | None = None
) -> None:
    query = sa.select(UserModel.id).where(sa.or_(UserModel.cellphone == cellphone, UserModel.username == cellphone))
    if exclude_id is not None:
        query = query.where(UserModel.id != exclude_id)
    if await session.scalar(query.limit(1)) is not None:
        raise UserAlreadyExistsError()
