#
# 密码哈希处理工具
#
# 提供密码的哈希加密和验证功能，使用 bcrypt 算法确保密码安全。
#

import bcrypt


def get_password_hash(password: str) -> str:
    """使用 bcrypt 哈希密码"""
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password=pwd_bytes, salt=salt)
    string_password = hashed_password.decode('utf8')
    return string_password


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """检查提供的密码是否与存储的密码（哈希后）匹配"""
    password_byte_enc = plain_password.encode('utf-8')
    hashed_password = hashed_password.encode('utf-8')
    try:
        result = bcrypt.checkpw(password_byte_enc, hashed_password)
    except ValueError:
        return False
    return result
