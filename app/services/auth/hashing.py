import bcrypt


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt"""
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password=pwd_bytes, salt=salt)
    string_password = hashed_password.decode('utf8')
    return string_password


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check if the provided password matches the stored password (hashed)"""
    password_byte_enc = plain_password.encode('utf-8')
    hashed_password = hashed_password.encode('utf-8')
    try:
        result = bcrypt.checkpw(password_byte_enc, hashed_password)
    except ValueError:
        return False
    return result
