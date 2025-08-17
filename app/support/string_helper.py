#
# 字符串处理辅助函数
#
# 提供字符串生成、验证和处理等常用功能。
#

import mimetypes
import random
import re
import string
from typing import Union

import magic


def get_bytes_mime_type(content: Union[str, bytes]) -> tuple[str, str]:
    """预测bytes的MIME类型和文件后缀

    Args:
        content: bytes

    Returns:
        MIME类型, 文件后缀
    """
    if isinstance(content, str):
        content = content.encode('utf-8')

    file_mime = magic.from_buffer(content, mime=True)
    suffix = None
    if file_mime is not None:
        suffix = mimetypes.guess_extension(file_mime)

    return file_mime, suffix


def alphanumeric_random(length: int = 16) -> str:
    """生成指定长度的字母和数字的随机字符串"""
    str_list = [random.choice(string.ascii_letters + string.digits) for i in range(length)]
    return ''.join(str_list)


def numeric_random(length: int) -> str:
    """生成指定长度的数字的随机字符串"""
    str_list = [random.choice(string.digits) for i in range(length)]
    return ''.join(str_list)


def is_chinese_cellphone(cellphone) -> bool:
    """判断号码是否为中国的手机号"""
    match = re.fullmatch(r'^1[3456789]\d{9}$', cellphone)
    return bool(match)


# Base64 正则表达式
_BASE64_PATTERN = re.compile(
    r'^(?:[A-Za-z0-9+/]{4})*'
    r'(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$'
)

# URL 安全的 Base64 正则表达式
_BASE64_URLSAFE_PATTERN = re.compile(
    r'^(?:[A-Za-z0-9\-_]{4})*'
    r'(?:[A-Za-z0-9\-_]{2}==|[A-Za-z0-9\-_]{3}=)?$'
)


def is_likely_base64(s: str, urlsafe: bool = False) -> bool:
    """快速判断字符串是否可能是 Base64 编码

    Args:
        s: 要检查的字符串
        urlsafe: 是否使用 URL 安全的 Base64 编码（默认为 False）

    Returns:
        如果字符串可能是 Base64 编码，返回 True；否则返回 False
    """
    # 1. 长度检查：Base64 字符串的长度必须是 4 的倍数
    if len(s) % 4 != 0:
        return False

    # 2. 选择正则表达式模式
    pattern = _BASE64_URLSAFE_PATTERN if urlsafe else _BASE64_PATTERN

    # 3. 字符集和填充检查
    if not pattern.match(s):
        return False

    # 通过所有检查，返回 True
    return True
