from pathlib import Path, PureWindowsPath
from typing import Annotated

from pydantic import StringConstraints, TypeAdapter, ValidationError

from app.exceptions import InvalidFileNameError

_LOCAL = TypeAdapter(Annotated[str, StringConstraints(min_length=1, max_length=255, pattern=r'^[\w.\-/\\]+$')])
_OBJECT = TypeAdapter(
    Annotated[str, StringConstraints(min_length=1, max_length=255, pattern=r'^[A-Za-z0-9_\-./一-鿿（）()]+$')]
)
_DEVICES = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{prefix}{n}' for prefix in ('COM', 'LPT') for n in range(1, 10)}


def check_file_name_safty(file_name: str, base_dir: str) -> str:
    """返回基目录内的相对路径；不解码URL，也不保证后续打开免于TOCTOU"""
    try:
        _LOCAL.validate_python(file_name)
    except ValidationError:
        raise InvalidFileNameError() from None

    # 同时拒绝POSIX和Windows绝对/驱动器/设备路径，不受当前平台影响
    normalized = file_name.replace('\\', '/')
    parts = normalized.split('/')
    if PureWindowsPath(file_name).drive or normalized.startswith('/') or len(parts) > 10:
        raise InvalidFileNameError()
    if any(
        part in ('', '.', '..') or part.endswith(('.', ' ')) or part.split('.')[0].upper() in _DEVICES for part in parts
    ):
        raise InvalidFileNameError()

    # resolve会跟随符号链接，包含深度检查在内的边界错误统一转换
    try:
        base = Path(base_dir).resolve()
        path = (base / Path(*parts)).resolve()
        path.relative_to(base)
    except (ValueError, OSError, RuntimeError):
        raise InvalidFileNameError() from None
    return str(path)


def check_oss_file_name_safety(file_name: str, base_dir: str | None = None) -> str:
    """校验对象存储相对key；base_dir仅作key前缀，不表示本地目录"""
    normalized = file_name.strip().replace('\\', '/')
    try:
        _OBJECT.validate_python(normalized)
    except ValidationError:
        raise InvalidFileNameError() from None

    parts = normalized.split('/')
    if len(parts) > 10 or any(part in ('', '.', '..') for part in parts):
        raise InvalidFileNameError()
    return f'{base_dir.rstrip("/")}/{normalized}' if base_dir else normalized
