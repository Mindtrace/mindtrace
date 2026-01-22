"""Unit test methods for mindtrace.core.utils.password utility module."""

import pytest

from mindtrace.core.utils.password import (
    _get_password_hasher,
    get_password_hasher,
    hash_password,
    verify_password,
)


class TestHashPassword:
    """Test hash_password function."""

    def test_hash_password_basic(self):
        """Test basic password hashing."""
        password = "test_password_123"
        hashed = hash_password(password)

        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != password  # Should not be plain text

    def test_hash_password_different_passwords_produce_different_hashes(self):
        """Test that different passwords produce different hashes."""
        password1 = "password1"
        password2 = "password2"

        hash1 = hash_password(password1)
        hash2 = hash_password(password2)

        assert hash1 != hash2

    def test_hash_password_same_password_produces_different_hashes(self):
        """Test that same password produces different hashes (due to salt)."""
        password = "same_password"

        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Argon2 uses salt, so same password should produce different hashes
        assert hash1 != hash2

    def test_hash_password_empty_string(self):
        """Test hashing an empty password."""
        hashed = hash_password("")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_special_characters(self):
        """Test hashing password with special characters."""
        password = "p@ssw0rd!#$%^&*()"
        hashed = hash_password(password)
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_unicode(self):
        """Test hashing password with unicode characters."""
        password = "密码🔒пароль"
        hashed = hash_password(password)
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_long_password(self):
        """Test hashing a very long password."""
        password = "a" * 1000
        hashed = hash_password(password)
        assert isinstance(hashed, str)
        assert len(hashed) > 0


class TestVerifyPassword:
    """Test verify_password function."""

    def test_verify_password_correct(self):
        """Test verifying a correct password."""
        password = "test_password_123"
        hashed = hash_password(password)

        result = verify_password(password, hashed)
        assert result is True

    def test_verify_password_incorrect(self):
        """Test verifying an incorrect password."""
        password = "correct_password"
        wrong_password = "wrong_password"
        hashed = hash_password(password)

        result = verify_password(wrong_password, hashed)
        assert result is False

    def test_verify_password_empty_string(self):
        """Test verifying an empty password."""
        password = ""
        hashed = hash_password(password)

        result = verify_password(password, hashed)
        assert result is True

        # Wrong empty password
        result_wrong = verify_password("not_empty", hashed)
        assert result_wrong is False

    def test_verify_password_case_sensitive(self):
        """Test that password verification is case sensitive."""
        password = "Password123"
        hashed = hash_password(password)

        assert verify_password("Password123", hashed) is True
        assert verify_password("password123", hashed) is False
        assert verify_password("PASSWORD123", hashed) is False

    def test_verify_password_special_characters(self):
        """Test verifying password with special characters."""
        password = "p@ssw0rd!#$%^&*()"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True
        assert verify_password("p@ssw0rd", hashed) is False

    def test_verify_password_unicode(self):
        """Test verifying password with unicode characters."""
        password = "密码🔒пароль"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True
        assert verify_password("密码", hashed) is False

    def test_verify_password_invalid_hash(self):
        """Test verifying with an invalid hash string."""
        from pwdlib.exceptions import UnknownHashError

        password = "test_password"
        invalid_hash = "not_a_valid_hash_string"

        # pwdlib raises UnknownHashError for invalid hash strings
        with pytest.raises(UnknownHashError):
            verify_password(password, invalid_hash)

    def test_verify_password_different_hash_format(self):
        """Test that hash from one password cannot verify another."""
        password1 = "password1"
        password2 = "password2"

        hash1 = hash_password(password1)
        hash2 = hash_password(password2)

        # Each hash should only verify its own password
        assert verify_password(password1, hash1) is True
        assert verify_password(password2, hash2) is True
        assert verify_password(password1, hash2) is False
        assert verify_password(password2, hash1) is False


class TestGetPasswordHasher:
    """Test get_password_hasher function."""

    def test_get_password_hasher_returns_instance(self):
        """Test that get_password_hasher returns a PasswordHash instance."""
        hasher = get_password_hasher()

        assert hasher is not None
        assert hasattr(hasher, "hash")
        assert hasattr(hasher, "verify")
        assert callable(hasher.hash)
        assert callable(hasher.verify)

    def test_get_password_hasher_singleton(self):
        """Test that get_password_hasher returns the same instance (singleton)."""
        hasher1 = get_password_hasher()
        hasher2 = get_password_hasher()

        assert hasher1 is hasher2

    def test_get_password_hasher_can_hash(self):
        """Test that returned hasher can hash passwords."""
        hasher = get_password_hasher()
        password = "test_password"

        hashed = hasher.hash(password)
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_get_password_hasher_can_verify(self):
        """Test that returned hasher can verify passwords."""
        hasher = get_password_hasher()
        password = "test_password"

        hashed = hasher.hash(password)
        assert hasher.verify(password, hashed) is True
        assert hasher.verify("wrong_password", hashed) is False


class TestGetPasswordHasherInternal:
    """Test _get_password_hasher internal function."""

    def test_get_password_hasher_internal_returns_instance(self):
        """Test that _get_password_hasher returns a PasswordHash instance."""
        hasher = _get_password_hasher()

        assert hasher is not None
        assert hasattr(hasher, "hash")
        assert hasattr(hasher, "verify")

    def test_get_password_hasher_internal_singleton(self):
        """Test that _get_password_hasher returns the same instance."""
        hasher1 = _get_password_hasher()
        hasher2 = _get_password_hasher()

        assert hasher1 is hasher2

    def test_get_password_hasher_internal_cached(self):
        """Test that _get_password_hasher caches the instance."""
        # Clear cache by deleting attribute if it exists
        if hasattr(_get_password_hasher, "cached_instance"):
            delattr(_get_password_hasher, "cached_instance")

        hasher1 = _get_password_hasher()
        assert hasattr(_get_password_hasher, "cached_instance")
        assert _get_password_hasher.cached_instance is hasher1

        hasher2 = _get_password_hasher()
        assert hasher2 is hasher1
        assert hasher2 is _get_password_hasher.cached_instance


class TestIntegration:
    """Integration tests for password utilities."""

    def test_hash_and_verify_workflow(self):
        """Test complete workflow of hashing and verifying."""
        password = "user_password_123"

        # Hash the password
        hashed = hash_password(password)

        # Verify it works
        assert verify_password(password, hashed) is True

        # Verify wrong password doesn't work
        assert verify_password("wrong_password", hashed) is False

    def test_multiple_passwords(self):
        """Test handling multiple different passwords."""
        passwords = ["password1", "password2", "password3", "p@ssw0rd!"]

        hashes = [hash_password(pwd) for pwd in passwords]

        # Each password should verify with its own hash
        for pwd, hashed in zip(passwords, hashes):
            assert verify_password(pwd, hashed) is True

        # Each password should NOT verify with other hashes
        for i, pwd in enumerate(passwords):
            for j, hashed in enumerate(hashes):
                if i != j:
                    assert verify_password(pwd, hashed) is False

    def test_get_password_hasher_and_direct_usage(self):
        """Test using get_password_hasher for direct hasher access."""
        hasher = get_password_hasher()
        password = "direct_usage_test"

        # Use hasher directly
        hashed = hasher.hash(password)
        assert hasher.verify(password, hashed) is True

        # Also works with utility functions
        assert verify_password(password, hashed) is True

    def test_consistency_between_functions(self):
        """Test that utility functions and direct hasher usage are consistent."""
        password = "consistency_test"
        hasher = get_password_hasher()

        # Hash using utility function
        hashed_util = hash_password(password)

        # Hash using direct hasher
        hashed_direct = hasher.hash(password)

        # Both should verify correctly
        assert verify_password(password, hashed_util) is True
        assert hasher.verify(password, hashed_direct) is True

        # Both should verify each other's hashes (same hasher instance)
        assert verify_password(password, hashed_direct) is True
        assert hasher.verify(password, hashed_util) is True
