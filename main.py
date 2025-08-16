import uvicorn

import app.providers.mimetypes_provider  # noqa: F401
from config.config import settings
from config.logging import settings as logging_settings

if __name__ == '__main__':
    if settings.DEBUG:
        # 开发环境配置：启用自动重载，单进程模式
        uvicorn.run(
            app='api_app:app',
            host=settings.SERVER_HOST,
            port=settings.SERVER_PORT,
            reload=True,
            workers=1,  # 单个进程
        )
    else:
        # 生产环境配置：禁用自动重载，启用多进程模式
        uvicorn.run(
            app='api_app:app',
            host=settings.SERVER_HOST,
            port=settings.SERVER_PORT,
            reload=False,  # 禁用自动重载
            workers=settings.WORKERS,  # 启用多进程模式，workers 数量可以根据需求调整
            timeout_keep_alive=120,  # 客户端与服务器之间的连接保持时间（秒）
            log_level=logging_settings.LOG_LEVEL.lower(),  # 设置日志级别为生产环境常用的 "info" 或 "warning"
        )
