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
    """返回解析后位于基目录内的绝对路径

    不执行 URL 解码，也不保证校验后再打开文件时仍位于基目录内。

    Raises:
        InvalidFileNameError: 相对路径不合规、无法解析或解析后超出基目录
    """
    # 限制相对路径文本的字符和长度
    try:
        _LOCAL.validate_python(file_name)
    except ValidationError:
        raise InvalidFileNameError() from None

    # 跨平台拒绝绝对路径、驱动器前缀和保留设备名
    normalized = file_name.replace('\\', '/')
    parts = normalized.split('/')
    if PureWindowsPath(file_name).drive or normalized.startswith('/') or len(parts) > 10:
        raise InvalidFileNameError()
    if any(
        part in ('', '.', '..') or part.endswith(('.', ' ')) or part.split('.')[0].upper() in _DEVICES for part in parts
    ):
        raise InvalidFileNameError()

    # 解析符号链接后仍须位于基目录内
    try:
        base = Path(base_dir).resolve()
        path = (base / Path(*parts)).resolve()
        path.relative_to(base)
    except (ValueError, OSError, RuntimeError):
        raise InvalidFileNameError() from None

    return str(path)


def check_oss_file_name_safety(file_name: str, base_dir: str | None = None) -> str:
    """校验相对对象键并返回带可选前缀的键，不解析本地路径

    Args:
        base_dir: 可信的键前缀，不参与相对键校验

    Raises:
        InvalidFileNameError: 相对对象键不合规
    """
    # 规范化对象 key 文本，不按本地文件系统解析
    normalized = file_name.strip().replace('\\', '/')
    try:
        _OBJECT.validate_python(normalized)
    except ValidationError:
        raise InvalidFileNameError() from None

    # 拒绝空段和目录跳转
    parts = normalized.split('/')
    if len(parts) > 10 or any(part in ('', '.', '..') for part in parts):
        raise InvalidFileNameError()

    return f'{base_dir.rstrip("/")}/{normalized}' if base_dir else normalized
