import hashlib
import mimetypes
import random
import re
import string
from typing import Union
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

import magic
from email_validator import EmailNotValidError, validate_email


def get_bytes_mime_type(content: Union[str, bytes]) -> tuple[str, str]:
    """
    预测bytes的MIME类型和文件后缀

    :param content: bytes
    :return: MIME类型, 文件后缀
    """
    if isinstance(content, str):
        content = content.encode('utf-8')

    file_mime = magic.from_buffer(content, mime=True)
    suffix = None
    if file_mime is not None:
        suffix = mimetypes.guess_extension(file_mime)

    return file_mime, suffix


def alphanumeric_random(length: int = 16) -> str:
    """
    生成指定长度的字母和数字的随机字符串
    """
    str_list = [random.choice(string.ascii_letters + string.digits) for i in range(length)]
    return ''.join(str_list)


def numeric_random(length: int) -> str:
    """
    生成指定长度的数字的随机字符串
    """
    str_list = [random.choice(string.digits) for i in range(length)]
    return ''.join(str_list)


def sha1_hash(content: Union[str, bytes]) -> str:
    """
    计算sha1

    :param content: 要计算的内容
    :return: sha1
    """
    sha1 = hashlib.sha1()
    sha1.update(type(content) == str and content.encode('utf-8') or content)
    return sha1.hexdigest()


def is_chinese_cellphone(cellphone) -> bool:
    """
    判断号码是否为中国的手机号
    """
    match = re.fullmatch(r'^1[3456789]\d{9}$', cellphone)
    return bool(match)


def is_valid_email(email: str, check_deliverability: bool = False) -> bool:
    """
    判断是否为有效的邮箱
    """
    try:
        emailinfo = validate_email(email, check_deliverability=check_deliverability)
        email = emailinfo.email
    except EmailNotValidError:
        return False
    return True


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
    """
    快速判断字符串是否可能是 Base64 编码。

    :param s: 要检查的字符串。
    :param urlsafe: 是否使用 URL 安全的 Base64 编码（默认为 False）。
    :return: 如果字符串可能是 Base64 编码，返回 True；否则返回 False。
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


def is_url(url: str) -> bool:
    """
    判断是否为有效的 URL
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def encode_url(url: str) -> str:
    """
    对 URL 的 path、query 和 fragment 部分进行编码

    :param url: 原始 URL
    :return: 编码后的 URL
    """
    # 解析 URL
    parsed_url = urlparse(url)

    # 编码 path、query 和 fragment
    encoded_path = quote(parsed_url.path)
    query_params = dict(parse_qsl(parsed_url.query))
    encoded_query = urlencode(query_params)
    encoded_fragment = quote(parsed_url.fragment)

    # 构建新的 URL
    new_url = urlunparse((
        parsed_url.scheme,
        parsed_url.netloc,
        encoded_path,
        parsed_url.params,
        encoded_query,
        encoded_fragment,
    ))

    return new_url
