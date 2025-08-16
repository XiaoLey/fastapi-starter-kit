#
# 哈希计算辅助函数
#
# 提供常用的哈希计算功能，如 SHA1 等。
#

import hashlib
from typing import Union


def sha1_hash(content: Union[str, bytes]) -> str:
    """计算sha1

    Args:
        content: 要计算的内容

    Returns:
        sha1
    """
    sha1 = hashlib.sha1()
    sha1.update(type(content) == str and content.encode('utf-8') or content)
    return sha1.hexdigest()
