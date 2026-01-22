"""Utility methods relating to password hashing and verification."""

from pwdlib import PasswordHash


def _get_password_hasher() -> PasswordHash:
    """Get or create the password hasher instance.

    Returns:
        PasswordHash instance with recommended settings
    """
    if not hasattr(_get_password_hasher, "cached_instance"):
        _get_password_hasher.cached_instance = PasswordHash.recommended()
    return _get_password_hasher.cached_instance


def get_password_hasher() -> PasswordHash:
    """Get the underlying PasswordHash instance for advanced usage.

    This allows access to all pwdlib features while providing a simple default interface via hash_password() and
    verify_password().

    Returns:
        PasswordHash instance with recommended settings

    Example:

            from mindtrace.core.utils.password import get_password_hasher

            hasher = get_password_hasher()
            custom_hash = hasher.hash("password", rounds=10)

    """
    return _get_password_hasher()


def hash_password(password: str) -> str:
    """Hash a password using Argon2.

    Uses pwdlib with Argon2 as recommended by FastAPI.

    Args:
        password: Plain text password to hash

    Returns:
        Hashed password string that can be safely stored in a database

    Example:

            hashed = hash_password("my_secure_password")
            user.hashed_password = hashed

    """
    return _get_password_hasher().hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Uses pwdlib with Argon2 to securely verify passwords.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password from database

    Returns:
        True if password matches, False otherwise

    Example:

            if verify_password(user_input, stored_hash):
                login_user()
            else:
                raise AuthenticationError()

    """
    return _get_password_hasher().verify(plain_password, hashed_password)


__all__ = [
    "hash_password",
    "verify_password",
    "get_password_hasher",
]
