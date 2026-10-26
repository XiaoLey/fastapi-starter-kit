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


async def create_account(
    session: AsyncSession,
    identities: Sequence[PreparedIdentity],
    *,
    profile: UserProfileSc | None = None,
    write_credentials: Callable[[AsyncSession, UUID], Awaitable[None]] | None = None,
) -> UserModel:
    """原子创建普通用户、身份和可选凭据，提交成功后返回

    调用方须先验证证明及可登录性。凭据回调使用给定会话写入，不得独立提交。

    Raises:
        ValueError: 没有提供身份
        UserAlreadyExistsError: 本次身份已被占用；其他数据库错误不转换
    """
    if not identities:
        raise ValueError('An account requires at least one prepared identity')

    # 保存点覆盖整个建号单元，唯一竞争不能留下孤儿用户
    async with session.begin_nested():
        user = await create_user(session, profile if profile is not None else UserProfileSc())
        session.add_all([
            AuthIdentityModel(
                user_id=user.id, namespace=item.namespace, subject=item.subject, verified_at=item.verified_at
            )
            for item in identities
        ])
        try:
            await session.flush()
        except IntegrityError as exc:
            # 仅翻译本次身份写入的目标唯一键，不吞凭据模块的同名约束错误
            original: BaseException | None = exc.orig
            for _ in range(4):
                if original is None:
                    break
                if (
                    getattr(original, 'sqlstate', None) == '23505'
                    and getattr(original, 'table_name', None) == AuthIdentityModel.__tablename__
                    and getattr(original, 'constraint_name', None) == 'uq_auth_identity_namespace_subject'
                ):
                    raise UserAlreadyExistsError() from None
                original = original.__cause__
            raise

        # 模块凭据与用户、身份共同成功或回滚
        if write_credentials is not None:
            await write_credentials(session, user.id)
            await session.flush()

    await session.commit()
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
