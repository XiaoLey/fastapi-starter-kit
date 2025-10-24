from pydantic import Field

from app.schemas.base import BaseSc
from app.types import GENDER_TYPE


class UserCreateRecvSc(BaseSc):
    """接收到的创建用户数据"""

    username: str = Field(description='用户名', example='admin')
    password: str | None = Field(None, description='密码', example='123456')
    nickname: str = Field(description='昵称', example='管理员', min_length=1)
    gender: GENDER_TYPE = Field(description='性别', example='male')
    cellphone: str = Field(description='手机号', example='12345678901')
    cellphone_verification_code: str = Field(description='手机号验证码', example='123456')
