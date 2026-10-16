"""Password hashing with the standard library's scrypt (no extra dependencies).

Stored format: scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>, so the cost settings
can be raised later without breaking existing hashes.
"""

import base64
import hashlib
import hmac
import secrets

N, R, P = 2**14, 8, 1
SALT_BYTES, KEY_BYTES = 16, 32


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=KEY_BYTES, maxmem=64 * 1024 * 1024)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(_scrypt(password, salt, N, R, P))}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, base64.b64decode(expected))


# Hash checked when a username doesn't exist, so a login takes the same time
# whether or not the account exists.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
