#
# 路径安全检查辅助函数
#
# 提供用于检查文件路径安全性的函数，防止路径遍历等安全问题。
#

import logging
import re
import urllib.parse
from pathlib import Path

from app.exceptions import InvalidFileNameError


def check_file_name_safty(file_name: str, base_dir: str) -> str:
    """检查文件名是否合法并返回安全的文件路径

    Args:
        file_name: 文件名
        base_dir: 基础目录

    Returns:
        安全的文件路径
    """

    # 最大文件名长度和路径深度
    MAX_FILENAME_LENGTH = 255
    MAX_PATH_DEPTH = 10

    # URL解码，直到字符串不再变化，防止多重编码攻击
    previous_file_name = ''
    while previous_file_name != file_name:
        previous_file_name = file_name
        file_name = urllib.parse.unquote(file_name)

    # 去除前导的路径分隔符，防止绝对路径
    file_name = file_name.lstrip('/\\')

    # 检查文件名是否包含非法字符
    if '..' in file_name or not re.match(r'^[\w\-.\\/]+$', file_name):
        logging.error(f'文件名包含非法字符或路径：{file_name}')
        raise InvalidFileNameError()

    # 构造路径
    base_path = Path(base_dir).resolve()
    file_path = (base_path / file_name).resolve()

    # 检查文件名长度
    if len(file_name) > MAX_FILENAME_LENGTH:
        logging.error(f'文件名过长：{file_name}')
        raise InvalidFileNameError()

    # 检查路径深度
    if len(file_path.relative_to(base_path).parts) > MAX_PATH_DEPTH:
        logging.error(f'路径层级过深：{file_name}')
        raise InvalidFileNameError()

    # 检查路径是否在基准路径内
    try:
        file_path.relative_to(base_path)
    except ValueError:
        logging.error(f'企图访问不允许的目录：{file_name}')
        raise InvalidFileNameError()

    return str(file_path)


def check_oss_file_name_safety(file_name: str, base_dir: str | None = None) -> str:
    """检查OSS文件名是否合法并返回安全的文件路径

    Args:
        file_name: 文件名
        base_dir: 基础目录

    Returns:
        安全的文件路径
    """

    # URL解码，直到字符串不再变化，防止多重编码攻击
    previous_file_name = ''
    while previous_file_name != file_name:
        previous_file_name = file_name
        file_name = urllib.parse.unquote(file_name)

    # 去除前导和尾随的空白字符
    file_name = file_name.strip()

    # 检查文件名长度，防止超长文件名
    MAX_FILENAME_LENGTH = 255
    if len(file_name) > MAX_FILENAME_LENGTH:
        logging.error(f'文件名过长：{file_name}')
        raise InvalidFileNameError()

    # 统一路径分隔符为 '/'，OSS使用 '/' 作为路径分隔符
    file_name = file_name.replace('\\', '/')

    # 替换连续的 '/' 为单个 '/'
    while '//' in file_name:
        file_name = file_name.replace('//', '/')

    # 去除前导的 '/'，防止绝对路径访问
    file_name = file_name.lstrip('/')

    # 拆分路径为各级目录
    parts = file_name.split('/')

    # 检查路径中是否包含不安全的部分
    # 禁止使用 '..'、'.' 或空的路径段，防止路径遍历和空路径
    if '..' in parts or '.' in parts or '' in parts:
        logging.error(f'文件路径含有不安全的引用：{file_name}')
        raise InvalidFileNameError()

    # 检查文件名中是否包含非法字符
    # 仅允许字母、数字、下划线、短划线、点、斜杠和中文
    ALLOWED_CHARS = re.compile(r'^[A-Za-z0-9_\-./\u4E00-\u9FFF（）()]+$')
    if not ALLOWED_CHARS.match(file_name):
        logging.error(f'文件名包含非法字符：{file_name}')
        raise InvalidFileNameError()

    # 限制路径深度，防止过深的目录层级
    MAX_PATH_DEPTH = 10
    if len(parts) > MAX_PATH_DEPTH:
        logging.error(f'路径层级过深：{file_name}')
        raise InvalidFileNameError()

    # 重新组装安全的路径
    safe_path = '/'.join(parts)

    # 组合基准目录和安全路径，确保文件访问在指定目录内
    if base_dir:
        # 去除 base_dir 尾部的斜杠，防止重复
        base_dir = base_dir.rstrip('/')
        full_path = f'{base_dir}/{safe_path}'
    else:
        full_path = safe_path

    return full_path
