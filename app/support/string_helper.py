import re
import secrets
import string


def numeric_random(length: int) -> str:
    """生成保留前导零的安全随机数字字符串"""
    if length < 0:
        raise ValueError('Length must be nonnegative')
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def is_likely_base64(s: str, urlsafe: bool = False) -> bool:
    """快速判断Base64字符和填充形态，不保证内容语义"""
    if len(s) % 4:
        return False
    alphabet = r'A-Za-z0-9_\-' if urlsafe else r'A-Za-z0-9+/'
    return re.fullmatch(rf'(?:[{alphabet}]{{4}})*(?:[{alphabet}]{{2}}==|[{alphabet}]{{3}}=)?', s) is not None
