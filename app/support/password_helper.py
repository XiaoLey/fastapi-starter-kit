"""密码计算不占用事件循环"""

from fastapi.concurrency import run_in_threadpool
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

_PASSWORD_HASH = PasswordHash((Argon2Hasher(),))
_DUMMY_HASH = '$argon2id$v=19$m=65536,t=3,p=4$ZZNQKgvV0oiNbh/uFH4lKA$YK19Sg7gLjYGoyshrf+Y8zwO31jI9TB6es7VgpbTsX4'


async def get_password_hash(password: str) -> str:
    """返回新密码的 Argon2 哈希"""
    return await run_in_threadpool(_PASSWORD_HASH.hash, password)


async def verify_password(plain_password: str, hashed_password: str | None) -> tuple[bool, str | None]:
    """校验密码，无可用哈希时按不匹配处理

    Returns:
        是否匹配及可选的替换哈希；仅匹配且需要升级时返回替换值
    """
    # 无密码账号也执行一次验证，不让账号存在性成为明显的快速分支
    try:
        valid, replacement = await run_in_threadpool(
            _PASSWORD_HASH.verify_and_update, plain_password, hashed_password or _DUMMY_HASH
        )
    except (ValueError, UnknownHashError):
        return False, None

    return (valid, replacement) if hashed_password else (False, None)
