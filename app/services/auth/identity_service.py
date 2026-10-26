from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AuthenticationError, UserAlreadyExistsError
from app.models.auth_identity import AuthIdentityModel
from app.models.user import UserModel
from app.schemas.user import UserProfileSc
from app.services.auth.user_service import create_user


class PreparedIdentity(BaseModel):
    """模块已规范化并完成所需证明的身份，只供服务端内部传递"""

    model_config = ConfigDict(frozen=True, extra='forbid')

    namespace: str = Field(min_length=1, max_length=128)
    subject: str = Field(min_length=1, max_length=512)
    verified_at: datetime | None = Field(default=None)


async def find_user(session: AsyncSession, *, namespace: str, subject: str) -> UserModel | None:
    """按完整身份域查询，包括已停用或软删除的归属"""
    return await session.scalar(
        sa
        .select(UserModel)
        .join(AuthIdentityModel)
        .where(AuthIdentityModel.namespace == namespace, AuthIdentityModel.subject == subject)
    )


def is_identity_conflict(exc: IntegrityError) -> bool:
    """只识别身份归属唯一键，不吞掉其他数据库错误"""
    original: BaseException | None = exc.orig
    for _ in range(4):
        if original is None:
            break
        if getattr(original, 'constraint_name', None) == 'uq_auth_identity_namespace_subject':
            return True
        original = original.__cause__
    return False


async def create_account(
    session: AsyncSession,
    identities: Sequence[PreparedIdentity],
    *,
    profile: UserProfileSc | None = None,
    write_credentials: Callable[[AsyncSession, UUID], Awaitable[None]] | None = None,
) -> UserModel:
    """原子创建普通用户、身份和可选凭据；身份占用整体冲突

    调用方须先验证证明及可登录性。凭据写入回调不得独立提交事务。
    """
    if not identities:
        raise ValueError('An account requires at least one prepared identity')

    # 保存点覆盖整个建号单元，唯一竞争不能留下孤儿用户
    try:
        async with session.begin_nested():
            user = await create_user(session, profile if profile is not None else UserProfileSc())
            session.add_all([
                AuthIdentityModel(
                    user_id=user.id, namespace=item.namespace, subject=item.subject, verified_at=item.verified_at
                )
                for item in identities
            ])
            await session.flush()
            if write_credentials is not None:
                await write_credentials(session, user.id)
                await session.flush()
        await session.commit()
    except IntegrityError as exc:
        if not is_identity_conflict(exc):
            raise
        raise UserAlreadyExistsError() from None

    return user


async def resolve_verified_user(session: AsyncSession, identity: PreparedIdentity) -> UserModel:
    """复用已验证身份或首次建号，不自动关联其他域的身份"""
    user = await find_user(session, namespace=identity.namespace, subject=identity.subject)
    if user is None:
        try:
            user = await create_account(session, [identity])
        except UserAlreadyExistsError:
            user = await find_user(session, namespace=identity.namespace, subject=identity.subject)
            if user is None:
                raise RuntimeError('Concurrent identity creation could not be resolved') from None

    if not user.is_enabled():
        raise AuthenticationError()
    return user
