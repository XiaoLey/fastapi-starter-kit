"""密码计算不占用事件循环；兼容读取历史 bcrypt"""

from fastapi.concurrency import run_in_threadpool
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

_PASSWORD_HASH = PasswordHash((Argon2Hasher(), BcryptHasher()))
_DUMMY_HASH = '$argon2id$v=19$m=65536,t=3,p=4$ZZNQKgvV0oiNbh/uFH4lKA$YK19Sg7gLjYGoyshrf+Y8zwO31jI9TB6es7VgpbTsX4'


async def get_password_hash(password: str) -> str:
    """返回新密码的 Argon2 哈希"""
    return await run_in_threadpool(_PASSWORD_HASH.hash, password)


async def verify_password(plain_password: str, hashed_password: str | None) -> tuple[bool, str | None]:
    """返回是否匹配及可选的新哈希；旧 bcrypt 超长输入不截断"""
    if hashed_password and hashed_password.startswith(('$2a$', '$2b$', '$2y$')):
        if len(plain_password.encode('utf-8')) > 72:
            return False, None

    # 无密码账号也执行一次验证，不让账号存在性成为明显的快速分支
    try:
        valid, replacement = await run_in_threadpool(
            _PASSWORD_HASH.verify_and_update, plain_password, hashed_password or _DUMMY_HASH
        )
    except (ValueError, UnknownHashError):
        return False, None

    return (valid, replacement) if hashed_password else (False, None)
