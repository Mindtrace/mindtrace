"""Unit test methods for mindtrace.core.utils.hashing utility module."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from mindtrace.core import compute_dir_hash
from mindtrace.core.utils.hashing import (
    PasswordHashPolicy,
    fingerprint,
    fingerprint_hasher,
    hash_password,
    needs_rehash,
    verify_and_maybe_upgrade,
    verify_password,
)


def test_compute_dir_hash_empty_directory():
    """Test computing hash of an empty directory."""
    with TemporaryDirectory() as temp_dir:
        hash_value = compute_dir_hash(temp_dir)

        # Hash should be deterministic (empty directory should always produce same hash)
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA256 produces 64 hex characters

        # Compute again to verify determinism
        hash_value2 = compute_dir_hash(temp_dir)
        assert hash_value == hash_value2


def test_compute_dir_hash_single_file():
    """Test computing hash of a directory with a single file."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_file = temp_path / "test.txt"
        test_file.write_text("Hello, World!")

        hash_value = compute_dir_hash(temp_dir)

        assert isinstance(hash_value, str)
        assert len(hash_value) == 64

        # Compute again to verify determinism
        hash_value2 = compute_dir_hash(temp_dir)
        assert hash_value == hash_value2


def test_compute_dir_hash_multiple_files():
    """Test computing hash of a directory with multiple files."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create multiple files
        (temp_path / "file1.txt").write_text("Content 1")
        (temp_path / "file2.txt").write_text("Content 2")
        (temp_path / "file3.txt").write_text("Content 3")

        hash_value = compute_dir_hash(temp_dir)

        assert isinstance(hash_value, str)
        assert len(hash_value) == 64

        # Compute again to verify determinism
        hash_value2 = compute_dir_hash(temp_dir)
        assert hash_value == hash_value2


def test_compute_dir_hash_nested_directories():
    """Test computing hash of a directory with nested subdirectories."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create nested structure
        (temp_path / "file1.txt").write_text("Root file")
        (temp_path / "subdir1").mkdir()
        (temp_path / "subdir1" / "file2.txt").write_text("Subdir file")
        (temp_path / "subdir1" / "subdir2").mkdir()
        (temp_path / "subdir1" / "subdir2" / "file3.txt").write_text("Nested file")

        hash_value = compute_dir_hash(temp_dir)

        assert isinstance(hash_value, str)
        assert len(hash_value) == 64

        # Compute again to verify determinism
        hash_value2 = compute_dir_hash(temp_dir)
        assert hash_value == hash_value2


def test_compute_dir_hash_deterministic():
    """Test that the same directory structure produces the same hash."""
    with TemporaryDirectory() as temp_dir1, TemporaryDirectory() as temp_dir2:
        temp_path1 = Path(temp_dir1)
        temp_path2 = Path(temp_dir2)

        # Create identical structures in both directories
        (temp_path1 / "file1.txt").write_text("Content")
        (temp_path1 / "subdir").mkdir()
        (temp_path1 / "subdir" / "file2.txt").write_text("Nested content")

        (temp_path2 / "file1.txt").write_text("Content")
        (temp_path2 / "subdir").mkdir()
        (temp_path2 / "subdir" / "file2.txt").write_text("Nested content")

        hash1 = compute_dir_hash(temp_dir1)
        hash2 = compute_dir_hash(temp_dir2)

        # Same structure should produce same hash
        assert hash1 == hash2


def test_compute_dir_hash_different_content():
    """Test that different file contents produce different hashes."""
    with TemporaryDirectory() as temp_dir1, TemporaryDirectory() as temp_dir2:
        temp_path1 = Path(temp_dir1)
        temp_path2 = Path(temp_dir2)

        # Create directories with same structure but different content
        (temp_path1 / "file.txt").write_text("Content 1")
        (temp_path2 / "file.txt").write_text("Content 2")

        hash1 = compute_dir_hash(temp_dir1)
        hash2 = compute_dir_hash(temp_dir2)

        # Different content should produce different hashes
        assert hash1 != hash2


def test_compute_dir_hash_different_structure():
    """Test that different directory structures produce different hashes."""
    with TemporaryDirectory() as temp_dir1, TemporaryDirectory() as temp_dir2:
        temp_path1 = Path(temp_dir1)
        temp_path2 = Path(temp_dir2)

        # Create directories with different structures
        (temp_path1 / "file1.txt").write_text("Content")
        (temp_path1 / "file2.txt").write_text("Content")

        (temp_path2 / "file1.txt").write_text("Content")
        (temp_path2 / "subdir").mkdir()
        (temp_path2 / "subdir" / "file2.txt").write_text("Content")

        hash1 = compute_dir_hash(temp_dir1)
        hash2 = compute_dir_hash(temp_dir2)

        # Different structure should produce different hashes
        assert hash1 != hash2


def test_compute_dir_hash_file_order_independent():
    """Test that file order doesn't matter (files are sorted)."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create files in one order
        (temp_path / "z_file.txt").write_text("Z content")
        (temp_path / "a_file.txt").write_text("A content")
        (temp_path / "m_file.txt").write_text("M content")

        hash1 = compute_dir_hash(temp_dir)

        # Delete and recreate in different order
        for f in temp_path.glob("*.txt"):
            f.unlink()

        (temp_path / "a_file.txt").write_text("A content")
        (temp_path / "m_file.txt").write_text("M content")
        (temp_path / "z_file.txt").write_text("Z content")

        hash2 = compute_dir_hash(temp_dir)

        # Should produce same hash regardless of creation order
        assert hash1 == hash2


def test_compute_dir_hash_ignores_directories():
    """Test that directories themselves are not hashed, only files."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create directory structure
        (temp_path / "file.txt").write_text("Content")
        (temp_path / "empty_dir").mkdir()

        hash_with_empty_dir = compute_dir_hash(temp_dir)

        # Remove empty directory
        (temp_path / "empty_dir").rmdir()

        hash_without_dir = compute_dir_hash(temp_dir)

        # Hash should be the same (empty directories don't affect hash)
        assert hash_with_empty_dir == hash_without_dir


def test_compute_dir_hash_accepts_path_object():
    """Test that compute_dir_hash accepts Path objects."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / "file.txt").write_text("Content")

        # Test with Path object
        hash_path = compute_dir_hash(temp_path)

        # Test with string
        hash_str = compute_dir_hash(temp_dir)

        # Should produce same hash
        assert hash_path == hash_str
        assert isinstance(hash_path, str)
        assert len(hash_path) == 64


def test_compute_dir_hash_accepts_string():
    """Test that compute_dir_hash accepts string paths."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / "file.txt").write_text("Content")

        # Test with string
        hash_str = compute_dir_hash(temp_dir)

        # Test with Path object
        hash_path = compute_dir_hash(temp_path)

        # Should produce same hash
        assert hash_str == hash_path
        assert isinstance(hash_str, str)
        assert len(hash_str) == 64


def test_compute_dir_hash_binary_files():
    """Test computing hash with binary file content."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create binary file
        binary_content = bytes([0x00, 0x01, 0x02, 0xFF, 0xFE, 0xFD])
        (temp_path / "binary.bin").write_bytes(binary_content)

        hash_value = compute_dir_hash(temp_dir)

        assert isinstance(hash_value, str)
        assert len(hash_value) == 64

        # Compute again to verify determinism
        hash_value2 = compute_dir_hash(temp_dir)
        assert hash_value == hash_value2


def test_compute_dir_hash_large_file():
    """Test computing hash with a larger file."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a larger file (1MB)
        large_content = "A" * (1024 * 1024)
        (temp_path / "large.txt").write_text(large_content)

        hash_value = compute_dir_hash(temp_dir)

        assert isinstance(hash_value, str)
        assert len(hash_value) == 64

        # Compute again to verify determinism
        hash_value2 = compute_dir_hash(temp_dir)
        assert hash_value == hash_value2


def test_compute_dir_hash_special_characters_in_path():
    """Test computing hash with special characters in file paths."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create files with special characters in names
        (temp_path / "file with spaces.txt").write_text("Content")
        (temp_path / "file-with-dashes.txt").write_text("Content")
        (temp_path / "file_with_underscores.txt").write_text("Content")
        (temp_path / "file.with.dots.txt").write_text("Content")

        hash_value = compute_dir_hash(temp_dir)

        assert isinstance(hash_value, str)
        assert len(hash_value) == 64

        # Compute again to verify determinism
        hash_value2 = compute_dir_hash(temp_dir)
        assert hash_value == hash_value2


# =============================================================================
# Fingerprint function tests
# =============================================================================


class TestFingerprint:
    """Tests for the fingerprint() function."""

    def test_fingerprint_default_sha256_hex(self):
        """Test default sha256 hex encoding."""
        result = fingerprint("hello world")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA256 produces 64 hex chars
        # Known SHA256 hash of "hello world"
        assert result == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_fingerprint_deterministic(self):
        """Test that fingerprint is deterministic."""
        data = "test data for hashing"
        result1 = fingerprint(data)
        result2 = fingerprint(data)
        assert result1 == result2

    def test_fingerprint_different_data_different_hash(self):
        """Test that different data produces different hashes."""
        hash1 = fingerprint("data1")
        hash2 = fingerprint("data2")
        assert hash1 != hash2

    def test_fingerprint_bytes_input(self):
        """Test fingerprint with bytes input."""
        text_result = fingerprint("hello")
        bytes_result = fingerprint(b"hello")
        assert text_result == bytes_result

    def test_fingerprint_sha512(self):
        """Test fingerprint with SHA512 algorithm."""
        result = fingerprint("test", alg="sha512")
        assert len(result) == 128  # SHA512 produces 128 hex chars

    def test_fingerprint_blake2b(self):
        """Test fingerprint with BLAKE2b algorithm."""
        result = fingerprint("test", alg="blake2b")
        assert len(result) == 128  # BLAKE2b default produces 64 bytes = 128 hex

    def test_fingerprint_blake2s(self):
        """Test fingerprint with BLAKE2s algorithm."""
        result = fingerprint("test", alg="blake2s")
        assert len(result) == 64  # BLAKE2s produces 32 bytes = 64 hex

    def test_fingerprint_md5(self):
        """Test fingerprint with MD5 algorithm (legacy support)."""
        result = fingerprint("test", alg="md5")
        assert len(result) == 32  # MD5 produces 16 bytes = 32 hex

    def test_fingerprint_sha1(self):
        """Test fingerprint with SHA1 algorithm (legacy support)."""
        result = fingerprint("test", alg="sha1")
        assert len(result) == 40  # SHA1 produces 20 bytes = 40 hex

    def test_fingerprint_b64_encoding(self):
        """Test fingerprint with base64 encoding."""
        result = fingerprint("test", encoding="b64")
        assert isinstance(result, str)
        # Base64 encoded SHA256 should end with padding
        assert "=" in result or len(result) == 44

    def test_fingerprint_b64url_encoding(self):
        """Test fingerprint with URL-safe base64 encoding (no padding)."""
        result = fingerprint("test", encoding="b64url")
        assert isinstance(result, str)
        assert "=" not in result  # No padding
        assert "+" not in result  # URL-safe
        assert "/" not in result  # URL-safe

    def test_fingerprint_invalid_encoding_raises(self):
        """Test that invalid encoding raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported encoding"):
            fingerprint("test", encoding="invalid")  # type: ignore

    def test_fingerprint_with_hmac_key(self):
        """Test fingerprint with HMAC key."""
        result_no_key = fingerprint("test")
        result_with_key = fingerprint("test", key="secret")
        assert result_no_key != result_with_key

    def test_fingerprint_hmac_deterministic(self):
        """Test that HMAC fingerprint is deterministic."""
        result1 = fingerprint("test", key="secret")
        result2 = fingerprint("test", key="secret")
        assert result1 == result2

    def test_fingerprint_different_keys_different_result(self):
        """Test that different HMAC keys produce different results."""
        result1 = fingerprint("test", key="key1")
        result2 = fingerprint("test", key="key2")
        assert result1 != result2

    def test_fingerprint_hmac_bytes_key(self):
        """Test HMAC with bytes key."""
        result_str = fingerprint("test", key="secret")
        result_bytes = fingerprint("test", key=b"secret")
        assert result_str == result_bytes


class TestFingerprintHasher:
    """Tests for the fingerprint_hasher() function."""

    def test_fingerprint_hasher_incremental(self):
        """Test incremental hashing with fingerprint_hasher."""
        h = fingerprint_hasher()
        h.update(b"hello ")
        h.update(b"world")
        incremental_result = h.hexdigest()

        direct_result = fingerprint("hello world")
        assert incremental_result == direct_result

    def test_fingerprint_hasher_with_key(self):
        """Test HMAC hasher creation."""
        h = fingerprint_hasher(key="secret")
        h.update(b"test")
        result = h.hexdigest()

        direct_result = fingerprint("test", key="secret")
        assert result == direct_result

    def test_fingerprint_hasher_different_algorithms(self):
        """Test hasher with different algorithms."""
        h_sha256 = fingerprint_hasher(alg="sha256")
        h_sha512 = fingerprint_hasher(alg="sha512")

        h_sha256.update(b"test")
        h_sha512.update(b"test")

        assert len(h_sha256.hexdigest()) == 64
        assert len(h_sha512.hexdigest()) == 128


# =============================================================================
# Password hashing tests
# =============================================================================


class TestHashPassword:
    """Tests for the hash_password() function."""

    def test_hash_password_argon2id_default(self):
        """Test password hashing with default argon2id."""
        hashed = hash_password("mypassword")
        assert hashed.startswith("$argon2id$")
        assert len(hashed) > 50

    def test_hash_password_bcrypt(self):
        """Test password hashing with bcrypt."""
        hashed = hash_password("mypassword", kdf="bcrypt")
        assert hashed.startswith("$2b$")

    def test_hash_password_scrypt(self):
        """Test password hashing with scrypt."""
        hashed = hash_password("mypassword", kdf="scrypt")
        assert hashed.startswith("$scrypt$")
        assert "N=" in hashed
        assert "r=" in hashed
        assert "p=" in hashed

    def test_hash_password_pbkdf2(self):
        """Test password hashing with PBKDF2."""
        hashed = hash_password("mypassword", kdf="pbkdf2_sha256")
        assert hashed.startswith("$pbkdf2_sha256$")
        assert "i=" in hashed

    def test_hash_password_unique_salts(self):
        """Test that each hash has a unique salt."""
        hash1 = hash_password("same_password")
        hash2 = hash_password("same_password")
        assert hash1 != hash2  # Different salts

    def test_hash_password_empty_raises(self):
        """Test that empty password raises ValueError."""
        with pytest.raises(ValueError, match="non-empty str"):
            hash_password("")

    def test_hash_password_non_string_raises(self):
        """Test that non-string password raises ValueError."""
        with pytest.raises(ValueError, match="non-empty str"):
            hash_password(12345)  # type: ignore

    def test_hash_password_unsupported_kdf_raises(self):
        """Test that unsupported KDF raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported password KDF"):
            hash_password("test", kdf="invalid_kdf")  # type: ignore

    def test_hash_password_custom_policy_bcrypt(self):
        """Test hash_password respects custom bcrypt rounds."""
        policy = PasswordHashPolicy(bcrypt_rounds=10)
        hashed = hash_password("test", kdf="bcrypt", policy=policy)
        # bcrypt format: $2b$<cost>$...
        cost = int(hashed.split("$")[2])
        assert cost == 10

    def test_hash_password_custom_policy_pbkdf2(self):
        """Test hash_password respects custom PBKDF2 iterations."""
        policy = PasswordHashPolicy(pbkdf2_iterations=100_000)
        hashed = hash_password("test", kdf="pbkdf2_sha256", policy=policy)
        assert "i=100000$" in hashed

    def test_hash_password_custom_policy_scrypt(self):
        """Test hash_password respects custom scrypt parameters."""
        policy = PasswordHashPolicy(scrypt_n=2**12, scrypt_r=4, scrypt_p=2)
        hashed = hash_password("test", kdf="scrypt", policy=policy)
        assert "N=4096$" in hashed
        assert "r=4$" in hashed
        assert "p=2$" in hashed

    def test_hash_password_custom_policy_argon2(self):
        """Test hash_password respects custom argon2 parameters."""
        # Use a non-default policy to exercise the custom hasher path
        custom_policy = PasswordHashPolicy(
            argon2_time_cost=2,
            argon2_memory_cost_kib=32 * 1024,
            argon2_parallelism=1,
        )
        hashed = hash_password("test", kdf="argon2id", policy=custom_policy)
        assert hashed.startswith("$argon2id$")
        # Verify the hash works
        assert verify_password(hashed, "test") is True


class TestVerifyPassword:
    """Tests for the verify_password() function."""

    def test_verify_password_argon2id_correct(self):
        """Test verifying correct password with argon2id."""
        hashed = hash_password("mypassword", kdf="argon2id")
        assert verify_password(hashed, "mypassword") is True

    def test_verify_password_argon2id_incorrect(self):
        """Test verifying incorrect password with argon2id."""
        hashed = hash_password("mypassword", kdf="argon2id")
        assert verify_password(hashed, "wrongpassword") is False

    def test_verify_password_bcrypt_correct(self):
        """Test verifying correct password with bcrypt."""
        hashed = hash_password("mypassword", kdf="bcrypt")
        assert verify_password(hashed, "mypassword") is True

    def test_verify_password_bcrypt_incorrect(self):
        """Test verifying incorrect password with bcrypt."""
        hashed = hash_password("mypassword", kdf="bcrypt")
        assert verify_password(hashed, "wrongpassword") is False

    def test_verify_password_scrypt_correct(self):
        """Test verifying correct password with scrypt."""
        hashed = hash_password("mypassword", kdf="scrypt")
        assert verify_password(hashed, "mypassword") is True

    def test_verify_password_scrypt_incorrect(self):
        """Test verifying incorrect password with scrypt."""
        hashed = hash_password("mypassword", kdf="scrypt")
        assert verify_password(hashed, "wrongpassword") is False

    def test_verify_password_pbkdf2_correct(self):
        """Test verifying correct password with PBKDF2."""
        hashed = hash_password("mypassword", kdf="pbkdf2_sha256")
        assert verify_password(hashed, "mypassword") is True

    def test_verify_password_pbkdf2_incorrect(self):
        """Test verifying incorrect password with PBKDF2."""
        hashed = hash_password("mypassword", kdf="pbkdf2_sha256")
        assert verify_password(hashed, "wrongpassword") is False

    def test_verify_password_empty_stored_hash_raises(self):
        """Test that empty stored hash raises ValueError."""
        with pytest.raises(ValueError, match="stored_hash must be a non-empty str"):
            verify_password("", "password")

    def test_verify_password_empty_password_raises(self):
        """Test that empty password raises ValueError."""
        hashed = hash_password("test")
        with pytest.raises(ValueError, match="password must be a non-empty str"):
            verify_password(hashed, "")

    def test_verify_password_non_string_stored_hash_raises(self):
        """Test that non-string stored hash raises ValueError."""
        with pytest.raises(ValueError, match="stored_hash must be a non-empty str"):
            verify_password(None, "password")  # type: ignore

    def test_verify_password_unknown_format_raises(self):
        """Test that unknown hash format raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported or unrecognized"):
            verify_password("not_a_valid_hash_format", "password")

    def test_verify_password_unicode_passwords(self):
        """Test password verification with unicode characters."""
        password = "pässwörd_日本語_🔐"
        hashed = hash_password(password)
        assert verify_password(hashed, password) is True
        assert verify_password(hashed, "wrong") is False

    def test_verify_password_malformed_argon2_raises(self):
        """Test that malformed argon2 hash raises ValueError."""
        # Valid prefix but malformed content
        with pytest.raises(ValueError, match="argon2 verification failed"):
            verify_password("$argon2id$v=19$m=invalid$corrupted_hash", "password")

    def test_verify_password_malformed_bcrypt_raises(self):
        """Test that malformed bcrypt hash raises ValueError."""
        # Valid prefix but malformed/truncated content
        with pytest.raises(ValueError, match="bcrypt verification failed"):
            verify_password("$2b$12$invalid_truncated_hash", "password")

    def test_verify_password_malformed_scrypt_raises(self):
        """Test that malformed scrypt hash raises ValueError."""
        # Matches regex with valid base64 chars, but invalid base64 padding (odd length)
        with pytest.raises(ValueError, match="scrypt verification failed"):
            verify_password("$scrypt$N=16384$r=8$p=1$salt=abc$dk=xyz", "password")

    def test_verify_password_malformed_pbkdf2_raises(self):
        """Test that malformed pbkdf2 hash raises ValueError."""
        # Matches regex with valid base64 chars, but invalid base64 padding
        with pytest.raises(ValueError, match="pbkdf2 verification failed"):
            verify_password("$pbkdf2_sha256$i=600000$salt=abc$dk=xyz", "password")


# =============================================================================
# needs_rehash tests
# =============================================================================


class TestNeedsRehash:
    """Tests for the needs_rehash() function."""

    def test_needs_rehash_same_policy_argon2(self):
        """Test that hash with same policy doesn't need rehash."""
        hashed = hash_password("test", kdf="argon2id")
        assert needs_rehash(hashed) is False

    def test_needs_rehash_different_kdf(self):
        """Test that hash with different KDF needs rehash."""
        # Hash with bcrypt but policy defaults to argon2id
        hashed = hash_password("test", kdf="bcrypt")
        assert needs_rehash(hashed) is True

    def test_needs_rehash_bcrypt_same_rounds(self):
        """Test bcrypt hash with same rounds doesn't need rehash."""
        policy = PasswordHashPolicy(default_kdf="bcrypt", bcrypt_rounds=12)
        hashed = hash_password("test", kdf="bcrypt", policy=policy)
        assert needs_rehash(hashed, policy=policy) is False

    def test_needs_rehash_bcrypt_different_rounds(self):
        """Test bcrypt hash with different rounds needs rehash."""
        old_policy = PasswordHashPolicy(default_kdf="bcrypt", bcrypt_rounds=10)
        new_policy = PasswordHashPolicy(default_kdf="bcrypt", bcrypt_rounds=12)
        hashed = hash_password("test", kdf="bcrypt", policy=old_policy)
        assert needs_rehash(hashed, policy=new_policy) is True

    def test_needs_rehash_scrypt_same_params(self):
        """Test scrypt hash with same params doesn't need rehash."""
        policy = PasswordHashPolicy(default_kdf="scrypt")
        hashed = hash_password("test", kdf="scrypt", policy=policy)
        assert needs_rehash(hashed, policy=policy) is False

    def test_needs_rehash_scrypt_different_n(self):
        """Test scrypt hash with different N needs rehash."""
        old_policy = PasswordHashPolicy(default_kdf="scrypt", scrypt_n=2**12)
        new_policy = PasswordHashPolicy(default_kdf="scrypt", scrypt_n=2**14)
        hashed = hash_password("test", kdf="scrypt", policy=old_policy)
        assert needs_rehash(hashed, policy=new_policy) is True

    def test_needs_rehash_pbkdf2_same_iterations(self):
        """Test PBKDF2 hash with same iterations doesn't need rehash."""
        policy = PasswordHashPolicy(default_kdf="pbkdf2_sha256")
        hashed = hash_password("test", kdf="pbkdf2_sha256", policy=policy)
        assert needs_rehash(hashed, policy=policy) is False

    def test_needs_rehash_pbkdf2_different_iterations(self):
        """Test PBKDF2 hash with different iterations needs rehash."""
        old_policy = PasswordHashPolicy(default_kdf="pbkdf2_sha256", pbkdf2_iterations=100_000)
        new_policy = PasswordHashPolicy(default_kdf="pbkdf2_sha256", pbkdf2_iterations=600_000)
        hashed = hash_password("test", kdf="pbkdf2_sha256", policy=old_policy)
        assert needs_rehash(hashed, policy=new_policy) is True

    def test_needs_rehash_empty_hash(self):
        """Test that empty hash needs rehash."""
        assert needs_rehash("") is True

    def test_needs_rehash_malformed_hash(self):
        """Test that malformed hash needs rehash."""
        assert needs_rehash("not_a_valid_hash") is True

    def test_needs_rehash_malformed_bcrypt(self):
        """Test that malformed bcrypt hash needs rehash."""
        policy = PasswordHashPolicy(default_kdf="bcrypt")
        # Malformed bcrypt (missing cost)
        assert needs_rehash("$2b$", policy=policy) is True

    def test_needs_rehash_malformed_argon2(self):
        """Test that malformed argon2 hash needs rehash."""
        # Malformed argon2 hash that will cause check_needs_rehash to fail
        assert needs_rehash("$argon2id$corrupted") is True

    def test_needs_rehash_malformed_scrypt_params(self):
        """Test that scrypt hash with non-integer params needs rehash."""
        policy = PasswordHashPolicy(default_kdf="scrypt")
        # Scrypt hash with non-integer N value (will fail int() conversion)
        assert needs_rehash("$scrypt$N=abc$r=8$p=1$salt=AAAA$dk=BBBB", policy=policy) is True

    def test_needs_rehash_malformed_pbkdf2_iterations(self):
        """Test that pbkdf2 hash with non-integer iterations needs rehash."""
        policy = PasswordHashPolicy(default_kdf="pbkdf2_sha256")
        # PBKDF2 hash with non-integer iteration count
        assert needs_rehash("$pbkdf2_sha256$i=notanumber$salt=AAAA$dk=BBBB", policy=policy) is True

    def test_needs_rehash_scrypt_hash_when_argon2_default(self):
        """Test scrypt hash needs rehash when default is argon2id."""
        # Create a valid scrypt hash
        scrypt_hash = hash_password("test", kdf="scrypt")
        # Default policy uses argon2id, so scrypt hash needs rehash
        assert needs_rehash(scrypt_hash) is True

    def test_needs_rehash_pbkdf2_hash_when_argon2_default(self):
        """Test pbkdf2 hash needs rehash when default is argon2id."""
        # Create a valid pbkdf2 hash
        pbkdf2_hash = hash_password("test", kdf="pbkdf2_sha256")
        # Default policy uses argon2id, so pbkdf2 hash needs rehash
        assert needs_rehash(pbkdf2_hash) is True

    def test_needs_rehash_scrypt_different_r(self):
        """Test scrypt hash with different r needs rehash."""
        old_policy = PasswordHashPolicy(default_kdf="scrypt", scrypt_r=4)
        new_policy = PasswordHashPolicy(default_kdf="scrypt", scrypt_r=8)
        hashed = hash_password("test", kdf="scrypt", policy=old_policy)
        assert needs_rehash(hashed, policy=new_policy) is True

    def test_needs_rehash_scrypt_different_p(self):
        """Test scrypt hash with different p needs rehash."""
        old_policy = PasswordHashPolicy(default_kdf="scrypt", scrypt_p=2)
        new_policy = PasswordHashPolicy(default_kdf="scrypt", scrypt_p=1)
        hashed = hash_password("test", kdf="scrypt", policy=old_policy)
        assert needs_rehash(hashed, policy=new_policy) is True


# =============================================================================
# verify_and_maybe_upgrade tests
# =============================================================================


class TestVerifyAndMaybeUpgrade:
    """Tests for the verify_and_maybe_upgrade() function."""

    def test_verify_and_upgrade_correct_no_upgrade_needed(self):
        """Test correct password with no upgrade needed."""
        hashed = hash_password("test")
        ok, new_hash = verify_and_maybe_upgrade(hashed, "test")
        assert ok is True
        assert new_hash is None

    def test_verify_and_upgrade_incorrect_password(self):
        """Test incorrect password returns False, None."""
        hashed = hash_password("test")
        ok, new_hash = verify_and_maybe_upgrade(hashed, "wrong")
        assert ok is False
        assert new_hash is None

    def test_verify_and_upgrade_needs_upgrade(self):
        """Test that upgrade returns new hash when needed."""
        # Hash with bcrypt, but default policy is argon2id
        old_hash = hash_password("test", kdf="bcrypt")
        ok, new_hash = verify_and_maybe_upgrade(old_hash, "test")
        assert ok is True
        assert new_hash is not None
        assert new_hash.startswith("$argon2id$")
        # New hash should also verify
        assert verify_password(new_hash, "test") is True

    def test_verify_and_upgrade_respects_policy(self):
        """Test that upgrade uses the provided policy."""
        old_hash = hash_password("test", kdf="argon2id")
        new_policy = PasswordHashPolicy(default_kdf="bcrypt")
        ok, new_hash = verify_and_maybe_upgrade(old_hash, "test", policy=new_policy)
        assert ok is True
        assert new_hash is not None
        assert new_hash.startswith("$2b$")

    def test_verify_and_upgrade_empty_password_raises(self):
        """Test that empty password raises."""
        hashed = hash_password("test")
        with pytest.raises(ValueError):
            verify_and_maybe_upgrade(hashed, "")


# =============================================================================
# compute_dir_hash extended tests
# =============================================================================


class TestComputeDirHashExtended:
    """Extended tests for compute_dir_hash with new parameters."""

    def test_compute_dir_hash_sha512(self):
        """Test directory hash with SHA512."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "file.txt").write_text("content")
            result = compute_dir_hash(temp_dir, alg="sha512")
            assert len(result) == 128  # SHA512 = 128 hex chars

    def test_compute_dir_hash_blake2b(self):
        """Test directory hash with BLAKE2b."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "file.txt").write_text("content")
            result = compute_dir_hash(temp_dir, alg="blake2b")
            assert len(result) == 128

    def test_compute_dir_hash_with_hmac_key(self):
        """Test directory hash with HMAC key."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "file.txt").write_text("content")

            hash_no_key = compute_dir_hash(temp_dir)
            hash_with_key = compute_dir_hash(temp_dir, key="secret")

            assert hash_no_key != hash_with_key

    def test_compute_dir_hash_hmac_deterministic(self):
        """Test that HMAC directory hash is deterministic."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "file.txt").write_text("content")

            hash1 = compute_dir_hash(temp_dir, key="secret")
            hash2 = compute_dir_hash(temp_dir, key="secret")

            assert hash1 == hash2

    def test_compute_dir_hash_different_keys_different_result(self):
        """Test that different HMAC keys produce different hashes."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "file.txt").write_text("content")

            hash1 = compute_dir_hash(temp_dir, key="key1")
            hash2 = compute_dir_hash(temp_dir, key="key2")

            assert hash1 != hash2

    def test_compute_dir_hash_not_found_raises(self):
        """Test that non-existent directory raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            compute_dir_hash("/nonexistent/path/that/does/not/exist")

    def test_compute_dir_hash_not_directory_raises(self):
        """Test that file path raises NotADirectoryError."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            file_path = temp_path / "file.txt"
            file_path.write_text("content")
            with pytest.raises(NotADirectoryError):
                compute_dir_hash(file_path)
