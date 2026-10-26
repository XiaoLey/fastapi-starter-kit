"""内置模板的可信注册入口；未选择的实现不参与装配"""

from app.services.auth.modules import AuthFactory, AuthModule
from config.settings import Settings


def builtin_factories() -> dict[str, AuthFactory]:
    """返回可选模板；只有选中模块才构造其路由"""

    def password(settings: Settings) -> AuthModule:
        from app.http.auth_methods.password import build_module

        return build_module(settings)

    def phone(settings: Settings) -> AuthModule:
        from app.http.auth_methods.phone_otp import build_module

        return build_module(settings)

    def email(settings: Settings) -> AuthModule:
        from app.http.auth_methods.email_otp import build_module

        return build_module(settings)

    return {'password': password, 'phone_otp': phone, 'email_otp': email}
