from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.http.deps import database_deps, request_deps
from app.schemas.common import BoolSc
from app.schemas.user import UserCreateReqSc
from app.services.auth import validation_service, verification_code_service
from app.services.auth.user_service import create_user

router = APIRouter(prefix='/users', tags=['用户'])


@router.post('', response_model=BoolSc, name='注册新用户')
async def register_user(
    user_create: UserCreateReqSc,
    client_ip: Annotated[str, Depends(request_deps.get_request_ip)],
    session: Annotated[AsyncSession, Depends(database_deps.get_db)],
):
    # 验证用户名
    await validation_service.validate_username_availability(session, user_create.username)
    # 验证手机号
    await validation_service.validate_cellphone_availability(session, user_create.cellphone)
    # 验证验证码
    await verification_code_service.verify_code(user_create.cellphone, user_create.cellphone_verification_code)

    await create_user(session, client_ip, user_create)
    await session.commit()
    return BoolSc(success=True)
