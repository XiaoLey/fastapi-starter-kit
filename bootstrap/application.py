from collections.abc import Callable, Sequence

from fastapi import FastAPI
from pydantic import ValidationError

from app.providers import app_provider, exception_provider, middleware_provider, route_provider
from app.providers.lifespan_provider import lifespan
from app.services.auth.modules import AuthModuleFactory, resolve_modules
from app.services.email.email_sender import EmailSender
from app.services.sms.sms_sender import SmsSender
from config.auth import JwtSettings
from config.settings import Settings, load_settings


def create_app(
    settings: Settings | None = None,
    *,
    auth_module_factories: Sequence[AuthModuleFactory] | None = None,
    sms_sender_factory: Callable[[], SmsSender] | None = None,
    email_sender_factory: Callable[[], EmailSender] | None = None,
) -> FastAPI:
    """组装独立应用，运行资源仅在lifespan内创建"""
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
            errors = [(error['loc'], error['type']) for error in exc.errors(include_input=False, include_context=False)]
            raise ValueError(f'Invalid local token settings: {errors}') from None

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

    # 公共边界先于路由组装，CORS置于可控错误输出之外
    exception_provider.register(app)
    middleware_provider.register(app)
    app_provider.register(app, settings)
    route_provider.boot(app, settings, modules)
    return app
