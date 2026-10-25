import sqlalchemy as sa
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AuthenticationError
from app.models.user import UserModel
from app.schemas.oauth2 import OAuth2CellphoneSc, OAuth2PasswordSc
from app.schemas.token import TokenSc
from app.services.auth import verification_code_service
from app.services.auth.token_service import create_token_response_from_user
from app.services.auth.user_service import create_user
from app.services.auth.validation_service import unique_field
from app.support import password_helper
from app.support.string_helper import alphanumeric_random
from config.settings import Settings


class PasswordGrant:
    """用户名或手机号密码登录"""

    def __init__(self, session: AsyncSession, settings: Settings, request_data: OAuth2PasswordSc) -> None:
        self.session = session
        self.settings = settings
        self.request_data = request_data

    async def respond(self) -> TokenSc:
        # 全历史跨列歧义不能由查询顺序或密码决定身份
        users = (
            await self.session.scalars(
                sa
                .select(UserModel)
                .where(
                    sa.or_(
                        UserModel.username == self.request_data.username,
                        UserModel.cellphone == self.request_data.username,
                    )
                )
                .limit(2)
            )
        ).all()
        user = users[0] if len(users) == 1 else None
        valid, replacement = await password_helper.verify_password(
            self.request_data.password.get_secret_value(), user.password if user is not None else None
        )
        if user is None or not valid or not user.is_enabled():
            raise AuthenticationError()

        # 升级哈希提交失败时不能返回成功凭据
        if replacement is not None:
            user.password = replacement
            await self.session.commit()
        return create_token_response_from_user(user, self.settings)


class CellphoneGrant:
    """验证码登录，首次创建普通无密码账号"""

    def __init__(
        self, session: AsyncSession, redis: Redis, settings: Settings, request_data: OAuth2CellphoneSc
    ) -> None:
        self.session = session
        self.redis = redis
        self.settings = settings
        self.request_data = request_data

    async def respond(self) -> TokenSc:
        cellphone = self.request_data.cellphone
        await verification_code_service.verify_code(
            self.redis, self.settings, cellphone=cellphone, code=self.request_data.verification_code, purpose='login'
        )
        user = await self.session.scalar(sa.select(UserModel).where(UserModel.cellphone == cellphone))

        # 保存点只包数据库创建，不重试验证码消费或整个登录
        if user is None:
            # 旧的数字用户名不能因首次手机号登录而产生第二个歧义身份
            if await self.session.scalar(sa.select(UserModel.id).where(UserModel.username == cellphone)) is not None:
                raise AuthenticationError()
            for _ in range(3):
                username = f'u_{alphanumeric_random(20)}'
                try:
                    async with self.session.begin_nested():
                        user = await create_user(
                            self.session, username=username, nickname=username, gender='unknown', cellphone=cellphone
                        )
                    break
                except IntegrityError as exc:
                    field = unique_field(exc)
                    if field == 'username':
                        continue
                    if field != 'cellphone':
                        raise
                    user = await self.session.scalar(sa.select(UserModel).where(UserModel.cellphone == cellphone))
                    break
            if user is None:
                raise RuntimeError('Account creation could not resolve a unique identity')
            if not user.is_enabled():
                raise AuthenticationError()
            await self.session.commit()

        if not user.is_enabled():
            raise AuthenticationError()
        return create_token_response_from_user(user, self.settings)
