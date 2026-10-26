from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSc
from app.types import GENDER_TYPE, USER_STATE_TYPE


class UserProfileSc(BaseSc):
    """初始建号可写资料，不接受权限或内部状态"""

    nickname: str = Field(default='新用户', min_length=1, max_length=255)
    gender: GENDER_TYPE = 'unknown'


class UserSc(BaseSc):
    """当前账号可读取的资料，不包含认证身份或秘密"""

    id: UUID
    nickname: str
    gender: GENDER_TYPE
    avatar: str
    state: USER_STATE_TYPE
    is_admin: bool
