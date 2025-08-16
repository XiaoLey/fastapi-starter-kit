from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import InvalidCellphoneCodeError
from app.http.deps import database_deps, request_deps
from app.schemas.common import BoolSc
from app.schemas.user import UserCreateRecvSc
from app.services.auth import verification_code_service
from app.services.auth.user_service import create_user

router = APIRouter(prefix='/users', tags=['用户'])


@router.post('', response_model=BoolSc, name='注册新用户')
async def register_user(
    user_create: UserCreateRecvSc,
    client_ip: Annotated[str, Depends(request_deps.get_request_ip)],
    session: Annotated[AsyncSession, Depends(database_deps.get_db)],
):
    if not await verification_code_service.verify(user_create.cellphone, user_create.cellphone_verify_code):
        raise InvalidCellphoneCodeError()

    await create_user(session, client_ip, user_create)
    await session.commit()
    return BoolSc(success=True)
