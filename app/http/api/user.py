from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import SmsUnavailableError, UserAlreadyExistsError
from app.http.deps import auth_deps, database_deps, firewall_deps
from app.http.deps.runtime_deps import get_resources, get_settings
from app.models.user import UserModel
from app.schemas.common import BoolSc
from app.schemas.user import UserCreateReqSc, UserSc
from app.services.auth import validation_service, verification_code_service
from app.services.auth.user_service import create_user
from app.support.password_helper import get_password_hash

router = APIRouter(prefix='/users', tags=['用户'])


@router.post('', status_code=201, response_model=BoolSc, dependencies=[Depends(firewall_deps.verify_register_limit)])
async def register_user(
    request: Request, user_create: UserCreateReqSc, session: Annotated[AsyncSession, Depends(database_deps.get_db)]
) -> BoolSc:
    settings = get_settings(request)
    if user_create.cellphone is not None and not settings.SMS_ENABLED:
        raise SmsUnavailableError()

    # 可用性是友好提示，最终唯一性仍由数据库处理并发保证
    await validation_service.validate_username_availability(session, user_create.username)
    if user_create.cellphone is not None:
        await validation_service.validate_cellphone_availability(session, user_create.cellphone)
        if user_create.cellphone_verification_code is None:
            raise RuntimeError('Validated registration is missing its phone code')
        await verification_code_service.verify_code(
            get_resources(request).redis_client,
            settings,
            cellphone=user_create.cellphone,
            code=user_create.cellphone_verification_code,
            purpose='register',
        )

    # 只映射公开可写字段，提交完成后才能返回成功
    password_hash = await get_password_hash(user_create.password.get_secret_value())
    try:
        await create_user(
            session,
            username=user_create.username,
            nickname=user_create.nickname,
            gender=user_create.gender,
            password_hash=password_hash,
            cellphone=user_create.cellphone,
        )
        await session.commit()
    except IntegrityError as exc:
        if validation_service.unique_field(exc) is None:
            raise
        raise UserAlreadyExistsError() from None
    return BoolSc()


@router.get('/me', response_model=UserSc)
async def me(user: Annotated[UserModel, Depends(auth_deps.get_auth_user)]) -> UserSc:
    return UserSc.model_validate(user)
