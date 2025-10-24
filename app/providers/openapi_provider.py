from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.exceptions import ErrorCode


def register(app: FastAPI):
    def create_patched_openapi():
        """创建并返回修改后的 OpenAPI schema"""
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(title=app.title, version=app.version, routes=app.routes)

        # 修改 components.schemas 中的 HTTPValidationError 定义
        if 'components' in openapi_schema and 'schemas' in openapi_schema['components']:
            if 'HTTPValidationError' in openapi_schema['components']['schemas']:
                original_schema = openapi_schema['components']['schemas']['HTTPValidationError']
                if 'properties' in original_schema:
                    # 创建新的 HTTPValidationError schema
                    new_schema = {
                        'type': 'object',
                        'properties': {
                            'code': {
                                'type': 'string',
                                'example': ErrorCode.VALIDATION_ERROR,
                                'description': 'Error code',
                            },
                            'message': {
                                'type': 'string',
                                'example': 'Validation failed',
                                'description': 'Error message',
                            },
                        },
                        'required': ['code', 'message'],
                    }

                    # 合并原有的 properties 和 required
                    new_schema['properties'].update(original_schema['properties'])
                    if 'required' in original_schema:
                        new_schema['required'].extend(original_schema['required'])
                    else:
                        new_schema['required'].append('detail')

                    # 更新 schema
                    openapi_schema['components']['schemas']['HTTPValidationError'] = new_schema

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = create_patched_openapi
