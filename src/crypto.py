"""Server-side password hashing using PBKDF2-HMAC-SHA256.

Paste content encryption is handled client-side via the Web Crypto API.
This module only handles optional password protection for access control.
"""

import hashlib
import os
import secrets


ITERATIONS = 600_000
KEY_LENGTH = 32
HASH_ALGORITHM = "sha256"


def hash_password(password: str) -> str:
    """Hash a password with a random salt using PBKDF2.

    Returns a string in the format: salt_hex$hash_hex
    """
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode("utf-8"),
        salt,
        ITERATIONS,
        dklen=KEY_LENGTH,
    )
    return f"{salt.hex()}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored PBKDF2 hash.

    The stored_hash format is: salt_hex$hash_hex
    """
    try:
        salt_hex, hash_hex = stored_hash.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False

    derived = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode("utf-8"),
        salt,
        ITERATIONS,
        dklen=KEY_LENGTH,
    )
    return secrets.compare_digest(derived, expected)
