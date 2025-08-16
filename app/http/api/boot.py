from fastapi import APIRouter

router = APIRouter(tags=['基础服务'])


@router.get('/ping')
def ping():
    return 'pong'
