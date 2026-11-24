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

    # 仅在没有提供工厂清单时使用内置认证方式
    if auth_module_factories is None:
        from app.http.auth_methods import builtin_factories

        auth_module_factories = builtin_factories()

    # 只构造配置选中的认证模块
    modules = resolve_modules(settings, auth_module_factories)

    # 仅在所选模块使用本地 token 时校验签发配置
    jwt_settings: JwtSettings | None = None
    if any(module.uses_local_tokens for module in modules):
        try:
            jwt_settings = JwtSettings.model_validate(settings.model_dump())
        except ValidationError as exc:
            # 只报告可公开的配置错误，不暴露秘密输入或原始异常链
            errors = [
                ValidationDetailSc.from_error(error).model_dump(exclude_none=True)
                for error in exc.errors(include_input=False)
            ]
            raise SafeValueError(f'Invalid local token settings: {errors}') from None

    # 调试模式开放开发文档，但不向客户端公开异常栈
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=False,
        lifespan=lifespan,
        docs_url='/docs' if settings.APP_DEBUG else None,
        redoc_url=None,
        openapi_url='/openapi.json' if settings.APP_DEBUG else None,
    )

    # 保存装配结果，运行资源留待应用启动时创建
    app.state.settings = settings
    app.state.auth_modules = modules
    app.state.jwt_settings = jwt_settings
    app.state.sms_sender_factory = sms_sender_factory
    app.state.email_sender_factory = email_sender_factory
    app.state.resources = None

    # 公共边界先于路由组装，CORS 置于可控错误输出之外
    exception_provider.register(app)
    middleware_provider.register(app, settings)

    # 装配路由并拒绝冲突的请求入口
    route_provider.boot(app, settings, modules)

    return app
