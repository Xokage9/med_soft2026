import secrets
import string

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from ..rules import GENERATED_PASSWORD_LEN

_ph = PasswordHasher()

_DUMMY_HASH = _ph.hash(secrets.token_urlsafe(16))

_ALPHABET = string.ascii_letters + string.digits


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _ph.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)


def generate_password(length: int = GENERATED_PASSWORD_LEN) -> str:
    while True:
        pwd = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if (any(c.islower() for c in pwd) and any(c.isupper() for c in pwd)
                and any(c.isdigit() for c in pwd)):
            return pwd


def check_admin_password_policy(password: str) -> str | None:
    from ..rules import ADMIN_PASSWORD_MIN
    if len(password) < ADMIN_PASSWORD_MIN:
        return f"Пароль должен быть не короче {ADMIN_PASSWORD_MIN} символов"
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return "Пароль должен содержать буквы и цифры"
    if password.lower() == password or password.upper() == password:
        return "Пароль должен содержать строчные и заглавные буквы"
    return None
