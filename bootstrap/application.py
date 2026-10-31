from collections.abc import Callable, Mapping

from fastapi import FastAPI
from pydantic import ValidationError

from app.exceptions import SafeValueError
from app.providers import exception_provider, middleware_provider, route_provider
from app.providers.lifespan_provider import lifespan
from app.schemas.common import ValidationDetailSc
from app.services.auth.modules import AuthFactory, resolve_modules
from app.services.email.email_sender import EmailSender
from app.services.sms.sms_sender import SmsSender
from config.auth import JwtSettings
from config.settings import Settings, load_settings


def create_app(
    settings: Settings | None = None,
    *,
    auth_module_factories: Mapping[str, AuthFactory] | None = None,
    sms_sender_factory: Callable[[], SmsSender] | None = None,
    email_sender_factory: Callable[[], EmailSender] | None = None,
) -> FastAPI:
    """组装独立应用，仅启用选中的认证，运行资源属于应用启动周期

    Args:
        settings: 省略时读取项目配置
        auth_module_factories: 名称到构造函数的映射；省略时使用内置清单，空映射不注册任何方式
        sms_sender_factory: 每轮启动创建新短信发送器的函数，仅需要该通道时调用
        email_sender_factory: 每轮启动创建新邮件发送器的函数，仅需要该通道时调用
    """
    settings = settings if settings is not None else load_settings()

    # 模块只解析一次，基础配置不强迫零认证应用提供密钥
    if auth_module_factories is None:
        from app.http.auth_methods import builtin_factories

        auth_module_factories = builtin_factories()
    modules = resolve_modules(settings, auth_module_factories)
    jwt_settings: JwtSettings | None = None
    if any(module.uses_local_tokens for module in modules):
        try:
            jwt_settings = JwtSettings.model_validate(settings.model_dump())
        except ValidationError as exc:
            errors = [
                ValidationDetailSc.from_error(error).model_dump(exclude_none=True)
                for error in exc.errors(include_input=False)
            ]
            raise SafeValueError(f'Invalid local token settings: {errors}') from None

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=False,
        lifespan=lifespan,
        docs_url='/docs' if settings.APP_DEBUG else None,
        redoc_url=None,
        openapi_url='/openapi.json' if settings.APP_DEBUG else None,
    )
    app.state.settings = settings
    app.state.auth_modules = modules
    app.state.jwt_settings = jwt_settings
    app.state.sms_sender_factory = sms_sender_factory
    app.state.email_sender_factory = email_sender_factory
    app.state.resources = None

    # 公共边界先于路由组装，CORS 置于可控错误输出之外
    exception_provider.register(app)
    middleware_provider.register(app, settings)
    route_provider.boot(app, settings, modules)
    return app
