import logging
import socket
import sys
import traceback
from pathlib import Path
from typing import override

from loguru import logger

from app.exceptions import SafeValueError
from config.settings import PROJECT_ROOT, Settings


class InterceptHandler(logging.Handler):
    """保留标准logging的调用位置，不转储异常输入和局部变量"""

    @override
    def emit(self, record: logging.LogRecord) -> None:
        if record.exc_info and record.exc_info[1] is not None:
            log_failure(record.exc_info[1])
            return

        # 跳过当前handler和logging自身的调用帧
        frame, depth = logging.currentframe(), 0
        while frame is not None and (depth == 0 or frame.f_code.co_filename in (logging.__file__, __file__)):
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth).log(record.levelno, record.getMessage())


_configuration: tuple[str, str | None, bool, str] | None = None


def _stdout_sink(message: str) -> None:
    sys.stdout.write(message)
    sys.stdout.flush()


def initialize(settings: Settings) -> None:
    """幂等配置进程日志；同进程不能隐式切换另一套日志配置"""
    global _configuration
    configuration = (
        settings.LOG_LEVEL,
        settings.LOG_PATH,
        settings.LOG_FILE_WITH_HOSTNAME_PREFIX,
        settings.LOG_RETENTION,
    )
    if _configuration is not None:
        if _configuration != configuration:
            raise RuntimeError('Conflicting process logging configuration')
        return

    # stdout是默认输出，文件只有显式指定后才创建
    logger.remove()
    logger.add(_stdout_sink, level=settings.LOG_LEVEL, diagnose=False, backtrace=False)
    if settings.LOG_PATH:
        hostname = socket.gethostname() if settings.LOG_FILE_WITH_HOSTNAME_PREFIX else ''
        path = Path(settings.LOG_PATH.replace('[hostname]', hostname))
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        logger.add(
            path,
            level=settings.LOG_LEVEL,
            rotation='00:00',
            retention=settings.LOG_RETENTION,
            diagnose=False,
            backtrace=False,
        )

    # 请求 URL 可能携带秘密，不启用第三方客户端的低级请求日志
    for name in ('httpx', 'httpcore'):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.basicConfig(handlers=[InterceptHandler()], level=settings.LOG_LEVEL)
    _configuration = configuration


def log_failure(exc: BaseException) -> None:
    """记录异常类型、位置和显式安全说明，不输出原始异常输入或局部值"""
    # 项目代码可直接定位，外部代码不暴露本机目录
    locations: list[str] = []
    for frame in traceback.extract_tb(exc.__traceback__):
        path = Path(frame.filename)
        path = path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else Path(path.name)
        locations.append(f'{path.as_posix()}:{frame.lineno}:{frame.name}')

    # 只有明确声明安全的校验说明可以进入日志
    reason = f': {exc}' if isinstance(exc, SafeValueError) else ''
    logger.error('{}{} [{}]', type(exc).__name__, reason, ' -> '.join(locations))
