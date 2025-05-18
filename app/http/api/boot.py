from fastapi import APIRouter

from app.schemas.common import BoolSc

router = APIRouter()


@router.get('/ping')
def ping():
    return "pong"


@router.get('/health', name='检查服务是否可用')
async def health():
    return BoolSc(success=True)
