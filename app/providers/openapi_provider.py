from fastapi import FastAPI
from fastapi.openapi.models import OAuth2, OpenAPI
from fastapi.openapi.utils import get_openapi

from config.settings import Settings


def register(app: FastAPI, settings: Settings) -> None:
    def create_openapi() -> dict[str, object]:
        if app.openapi_schema is not None:
            return app.openapi_schema

        # 仅配置本项目公开的security scheme，不篡改框架内部校验schema
        schema = OpenAPI.model_validate(get_openapi(title=app.title, version=app.version, routes=app.routes))
        if schema.components and schema.components.securitySchemes:
            scheme = schema.components.securitySchemes.get('PasswordBearer')
            if isinstance(scheme, OAuth2) and scheme.flows.password:
                scheme.flows.password.tokenUrl = f'{settings.APP_API_PREFIX}/auth/token/password'
        app.openapi_schema = schema.model_dump(mode='json', by_alias=True, exclude_none=True)
        return app.openapi_schema

    app.openapi = create_openapi
