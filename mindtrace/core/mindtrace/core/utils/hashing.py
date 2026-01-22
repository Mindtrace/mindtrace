"""Hashing utilities for fingerprinting and password management.

This module provides:
- Fast fingerprinting functions for general-purpose hashing (identifiers, cache keys, etc.)
- Secure password hashing with multiple KDF algorithms (Argon2id, bcrypt, scrypt, PBKDF2)
- Password verification with automatic hash format detection
- Hash upgrade utilities for migrating between algorithms/parameters
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError as Argon2VerifyMismatchError

# =============================================================================
# Type Definitions
# =============================================================================

# Note: sha1 and md5 are included for compatibility/legacy use cases only.
# Prefer sha256, sha512, or blake2b for new applications.
FingerprintAlg = Literal["sha256", "sha512", "blake2b", "blake2s", "sha1", "md5"]
FingerprintEncoding = Literal["hex", "b64", "b64url"]

PasswordKDF = Literal["argon2id", "bcrypt", "scrypt", "pbkdf2_sha256"]


# =============================================================================
# Configuration Classes
# =============================================================================


@dataclass(frozen=True)
class PasswordHashPolicy:
    """Holds password hashing defaults.

    Tune these to match your environment and latency targets. The defaults are
    a reasonable starting point for many services, but you should benchmark on
    production-like hardware.

    Attributes:
        default_kdf: Algorithm to use for newly created password hashes.
        argon2_time_cost: Argon2 time cost (iterations).
        argon2_memory_cost_kib: Argon2 memory cost in KiB.
        argon2_parallelism: Argon2 parallelism (lanes/threads).
        argon2_hash_len: Length of derived key in bytes.
        argon2_salt_len: Salt length in bytes.
        bcrypt_rounds: bcrypt work factor (cost).
        scrypt_n: scrypt CPU/memory cost parameter N (must be power of two).
        scrypt_r: scrypt block size parameter r.
        scrypt_p: scrypt parallelization parameter p.
        scrypt_dklen: scrypt derived key length in bytes.
        scrypt_salt_len: scrypt salt length in bytes.
        pbkdf2_iterations: PBKDF2 iteration count.
        pbkdf2_salt_len: PBKDF2 salt length in bytes.
        pbkdf2_dklen: PBKDF2 derived key length in bytes.
        pbkdf2_hash_name: Hash name for PBKDF2 (e.g., "sha256").
    """

    default_kdf: PasswordKDF = "argon2id"

    # Argon2id (argon2-cffi). memory_cost is KiB.
    argon2_time_cost: int = 3
    argon2_memory_cost_kib: int = 64 * 1024  # 64 MiB
    argon2_parallelism: int = 2
    argon2_hash_len: int = 32
    argon2_salt_len: int = 16

    # bcrypt
    bcrypt_rounds: int = 12

    # scrypt (hashlib.scrypt)
    scrypt_n: int = 2**14
    scrypt_r: int = 8
    scrypt_p: int = 1
    scrypt_dklen: int = 32
    scrypt_salt_len: int = 16

    # PBKDF2-HMAC-SHA256
    pbkdf2_iterations: int = 600_000
    pbkdf2_salt_len: int = 16
    pbkdf2_dklen: int = 32
    pbkdf2_hash_name: str = "sha256"


DEFAULT_PASSWORD_HASH_POLICY = PasswordHashPolicy()


# =============================================================================
# Fingerprint Functions (Public API)
# =============================================================================


def fingerprint_hasher(
    *,
    alg: FingerprintAlg = "sha256",
    key: str | bytes | None = None,
):
    """Creates an incremental fingerprint hasher.

    This returns an object supporting `update(data: bytes)` and `digest()` /
    `hexdigest()`, suitable for hashing streaming data.

    If `key` is provided, the returned object is an HMAC instance using the given
    digest algorithm. If `key` is not provided, the returned object is a
    `hashlib` hash instance.

    Args:
        alg: Digest algorithm to use (e.g., "sha256", "blake2b").
        key: Optional secret key to compute an HMAC instead of a plain digest.

    Returns:
        A hash-like object (hashlib hasher or HMAC) supporting incremental updates.

    Raises:
        AttributeError: If `alg` is not available in `hashlib`.
    """
    digest_ctor = getattr(hashlib, alg)  # may raise AttributeError intentionally
    if key is None:
        return digest_ctor()

    key_b = _to_bytes(key)
    return hmac.new(key_b, digestmod=digest_ctor)


def fingerprint(
    data: str | bytes,
    *,
    alg: FingerprintAlg = "sha256",
    key: str | bytes | None = None,
    encoding: FingerprintEncoding = "hex",
) -> str:
    """Computes a fast general-purpose fingerprint (digest or HMAC).

    This is intended for identifiers, cache keys, integrity checks, etc.

    Warning:
        Do not use this for password storage. Use a password KDF like Argon2id,
        bcrypt, scrypt, or PBKDF2.

    Args:
        data: Data to fingerprint.
        alg: Digest algorithm to use.
        key: Optional secret key. If provided, computes HMAC(alg, key, data).
        encoding: Output encoding:
            - "hex": lowercase hex string (default)
            - "b64": base64 string (standard alphabet, includes padding)
            - "b64url": URL-safe base64 without padding

    Returns:
        Encoded fingerprint string.

    Raises:
        AttributeError: If `alg` is not available in `hashlib`.
        ValueError: If `encoding` is not supported.
    """
    h = fingerprint_hasher(alg=alg, key=key)
    h.update(_to_bytes(data))
    digest = h.digest()

    if encoding == "hex":
        return digest.hex()
    if encoding == "b64":
        return base64.b64encode(digest).decode("ascii")
    if encoding == "b64url":
        return _b64url_nopad(digest)
    raise ValueError(f"Unsupported encoding: {encoding}")


def compute_dir_hash(
    directory_path: str | Path,
    chunk_size: int = 2**20,
    *,
    alg: FingerprintAlg = "sha256",
    key: str | bytes | None = None,
) -> str:
    """Computes a deterministic fingerprint of a directory's contents.

    The hash is deterministic across runs and stable across platforms:
    - Files are sorted by their relative POSIX paths.
    - For each file, the hash includes:
        1) a marker + relative path
        2) a marker + file contents (streamed in chunks)
        3) a file-boundary marker

    The boundary markers avoid ambiguity between path and content concatenation.

    If `key` is provided, the hash becomes an HMAC, which is appropriate when you
    need tamper-detection against an attacker who can modify directory contents.

    Args:
        directory_path: Path to the directory to hash.
        chunk_size: Size of read chunks in bytes.
        alg: Digest algorithm to use (default "sha256").
        key: Optional secret key for HMAC.

    Returns:
        Lowercase hexadecimal digest string.

    Raises:
        FileNotFoundError: If `directory_path` does not exist.
        NotADirectoryError: If `directory_path` is not a directory.
        OSError: For I/O errors while reading files.
        AttributeError: If `alg` is not available in `hashlib`.
    """
    directory_path = Path(directory_path)
    if not directory_path.exists():
        raise FileNotFoundError(directory_path)
    if not directory_path.is_dir():
        raise NotADirectoryError(directory_path)

    h = fingerprint_hasher(alg=alg, key=key)

    files = sorted(
        (p for p in directory_path.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(directory_path).as_posix(),
    )

    for file_path in files:
        rel_path = file_path.relative_to(directory_path).as_posix().encode("utf-8")

        # Path marker + path + content marker
        h.update(b"P\0")
        h.update(rel_path)
        h.update(b"\0C\0")

        with open(file_path, "rb") as fp:
            while True:
                chunk = fp.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)

        # File boundary marker
        h.update(b"\0F\0")

    return h.hexdigest()


# =============================================================================
# Password Hashing Functions (Public API)
# =============================================================================


def hash_password(
    password: str,
    *,
    kdf: PasswordKDF | None = None,
    policy: PasswordHashPolicy = DEFAULT_PASSWORD_HASH_POLICY,
) -> str:
    """Hashes a password using a slow password KDF.

    The returned string is self-describing and safe to store. Verification uses
    the stored hash's prefix/format to select the correct verifier.

    Args:
        password: Plaintext password (unicode string).
        kdf: Optional algorithm override. If not provided, uses
            `policy.default_kdf`.
        policy: Password hashing policy and parameters.

    Returns:
        Encoded password hash string.

    Raises:
        ValueError: If inputs are invalid or KDF is unsupported.
    """
    if not isinstance(password, str) or password == "":
        raise ValueError("password must be a non-empty str")

    chosen = kdf or policy.default_kdf
    pw_b = password.encode("utf-8")

    if chosen == "argon2id":
        return _get_argon2_hasher(policy).hash(password)

    if chosen == "bcrypt":
        salt = bcrypt.gensalt(rounds=policy.bcrypt_rounds)
        return bcrypt.hashpw(pw_b, salt).decode("utf-8")

    if chosen == "scrypt":
        salt = os.urandom(policy.scrypt_salt_len)
        dk = hashlib.scrypt(
            pw_b,
            salt=salt,
            n=policy.scrypt_n,
            r=policy.scrypt_r,
            p=policy.scrypt_p,
            dklen=policy.scrypt_dklen,
        )
        return f"$scrypt$N={policy.scrypt_n}$r={policy.scrypt_r}$p={policy.scrypt_p}$salt={_b64e(salt)}$dk={_b64e(dk)}"

    if chosen == "pbkdf2_sha256":
        salt = os.urandom(policy.pbkdf2_salt_len)
        dk = hashlib.pbkdf2_hmac(
            policy.pbkdf2_hash_name,
            pw_b,
            salt,
            policy.pbkdf2_iterations,
            dklen=policy.pbkdf2_dklen,
        )
        return f"$pbkdf2_sha256$i={policy.pbkdf2_iterations}$salt={_b64e(salt)}$dk={_b64e(dk)}"

    raise ValueError(f"Unsupported password KDF: {chosen}")


def verify_password(stored_hash: str, password: str) -> bool:
    """Verifies a candidate password against a stored password hash.

    Returns False for mismatches. Raises an error for malformed/unsupported hash
    formats.

    Args:
        stored_hash: Stored password hash string.
        password: Candidate plaintext password.

    Returns:
        True if the password matches, False otherwise.

    Raises:
        ValueError: If the stored hash format is malformed or unsupported.
    """
    if not isinstance(stored_hash, str) or stored_hash == "":
        raise ValueError("stored_hash must be a non-empty str")
    if not isinstance(password, str) or password == "":
        raise ValueError("password must be a non-empty str")

    pw_b = password.encode("utf-8")

    # Argon2 hashes start with "$argon2..."
    if stored_hash.startswith("$argon2"):
        try:
            # Use default policy hasher for verification (params are in the hash)
            return _get_argon2_hasher(DEFAULT_PASSWORD_HASH_POLICY).verify(stored_hash, password)
        except Argon2VerifyMismatchError:
            return False
        except Exception as e:
            raise ValueError(f"argon2 verification failed: {e}") from e

    # bcrypt hashes typically start with "$2a$", "$2b$", or "$2y$"
    if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(pw_b, stored_hash.encode("utf-8"))
        except Exception as e:
            raise ValueError(f"bcrypt verification failed: {e}") from e

    # scrypt custom encoding
    m = _SCRYPT_RE.match(stored_hash)
    if m:
        try:
            N = int(m.group("N"))
            r = int(m.group("r"))
            p = int(m.group("p"))
            salt = _b64d(m.group("salt"))
            dk_expected = _b64d(m.group("dk"))
            dk_actual = hashlib.scrypt(pw_b, salt=salt, n=N, r=r, p=p, dklen=len(dk_expected))
            return hmac.compare_digest(dk_actual, dk_expected)
        except Exception as e:
            raise ValueError(f"scrypt verification failed: {e}") from e

    # pbkdf2 custom encoding
    m = _PBKDF2_RE.match(stored_hash)
    if m:
        try:
            iters = int(m.group("i"))
            salt = _b64d(m.group("salt"))
            dk_expected = _b64d(m.group("dk"))
            dk_actual = hashlib.pbkdf2_hmac("sha256", pw_b, salt, iters, dklen=len(dk_expected))
            return hmac.compare_digest(dk_actual, dk_expected)
        except Exception as e:
            raise ValueError(f"pbkdf2 verification failed: {e}") from e

    raise ValueError("Unsupported or unrecognized stored hash format")


def needs_rehash(
    stored_hash: str,
    *,
    policy: PasswordHashPolicy = DEFAULT_PASSWORD_HASH_POLICY,
) -> bool:
    """Checks whether a stored password hash should be upgraded.

    This enables incremental upgrades when you change algorithms or parameters:
    verify on login, then re-hash with current policy and store the new hash.

    Behavior:
        - If the stored hash uses a different algorithm than `policy.default_kdf`,
          returns True.
        - If the stored hash uses the same algorithm but different parameters,
          returns True.
        - For malformed/unknown hashes, returns True.

    Args:
        stored_hash: Stored password hash string.
        policy: Current password hashing policy.

    Returns:
        True if the stored hash should be upgraded; False otherwise.
    """
    if not isinstance(stored_hash, str) or stored_hash == "":
        return True

    desired = policy.default_kdf

    if stored_hash.startswith("$argon2"):
        if desired != "argon2id":
            return True
        try:
            return _get_argon2_hasher(policy).check_needs_rehash(stored_hash)
        except (ValueError, TypeError):
            # Malformed hash string
            return True

    if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
        if desired != "bcrypt":
            return True
        try:
            cost = int(stored_hash.split("$")[2])
            return cost != policy.bcrypt_rounds
        except (ValueError, IndexError):
            # Malformed hash string
            return True

    m = _SCRYPT_RE.match(stored_hash)
    if m:
        if desired != "scrypt":
            return True
        # Regex guarantees N, r, p are valid digit strings
        return not (
            int(m.group("N")) == policy.scrypt_n
            and int(m.group("r")) == policy.scrypt_r
            and int(m.group("p")) == policy.scrypt_p
        )

    m = _PBKDF2_RE.match(stored_hash)
    if m:
        if desired != "pbkdf2_sha256":
            return True
        # Regex guarantees i is a valid digit string
        return int(m.group("i")) != policy.pbkdf2_iterations

    return True


def verify_and_maybe_upgrade(
    stored_hash: str,
    password: str,
    *,
    policy: PasswordHashPolicy = DEFAULT_PASSWORD_HASH_POLICY,
) -> tuple[bool, str | None]:
    """Verifies a password and optionally returns an upgraded hash.

    This is designed for login flows:
        1) Verify password against stored hash.
        2) If it matches and `needs_rehash(...)` is True, return a new hash
           computed with the current policy.

    Args:
        stored_hash: Stored password hash string.
        password: Candidate plaintext password.
        policy: Password hashing policy used for the upgrade decision.

    Returns:
        A tuple (ok, new_hash):
            - ok: True if password verified, else False.
            - new_hash: A new hash to store if upgrade is needed; otherwise None.

    Raises:
        ValueError: If stored hash format is malformed/unsupported.
        ValueError: If password is empty or not a string.
    """
    ok = verify_password(stored_hash, password)
    if not ok:
        return False, None

    if needs_rehash(stored_hash, policy=policy):
        return True, hash_password(password, kdf=policy.default_kdf, policy=policy)

    return True, None


# =============================================================================
# Private Helper Functions
# =============================================================================


def _to_bytes(data: str | bytes, *, encoding: str = "utf-8") -> bytes:
    """Converts text/bytes input to bytes."""
    return data if isinstance(data, bytes) else data.encode(encoding)


def _b64url_nopad(raw: bytes) -> str:
    """Encodes bytes as URL-safe base64 without '=' padding."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64e(raw: bytes) -> str:
    """Encodes bytes as standard base64 (with padding)."""
    return base64.b64encode(raw).decode("ascii")


def _b64d(s: str) -> bytes:
    """Decodes standard base64 (with padding)."""
    return base64.b64decode(s.encode("ascii"), validate=True)


def _get_argon2_hasher(policy: PasswordHashPolicy) -> PasswordHasher:
    """Returns an Argon2 PasswordHasher configured for the given policy.

    For the default policy, returns a cached singleton to avoid repeated
    instantiation overhead. For custom policies, creates a new hasher.
    """
    global _DEFAULT_ARGON2_PH

    # Fast path: reuse cached hasher for default policy
    if policy is DEFAULT_PASSWORD_HASH_POLICY:
        if _DEFAULT_ARGON2_PH is None:
            _DEFAULT_ARGON2_PH = PasswordHasher(
                time_cost=policy.argon2_time_cost,
                memory_cost=policy.argon2_memory_cost_kib,
                parallelism=policy.argon2_parallelism,
                hash_len=policy.argon2_hash_len,
                salt_len=policy.argon2_salt_len,
            )
        return _DEFAULT_ARGON2_PH

    # Custom policy: create a new hasher with the specified parameters
    return PasswordHasher(
        time_cost=policy.argon2_time_cost,
        memory_cost=policy.argon2_memory_cost_kib,
        parallelism=policy.argon2_parallelism,
        hash_len=policy.argon2_hash_len,
        salt_len=policy.argon2_salt_len,
    )


# =============================================================================
# Module-level State and Constants
# =============================================================================

# Lazily-initialized Argon2 hasher for default policy (avoids import-time cost).
_DEFAULT_ARGON2_PH: PasswordHasher | None = None

# Self-describing formats for scrypt/pbkdf2:
#   $scrypt$N=<N>$r=<r>$p=<p>$salt=<b64>$dk=<b64>
#   $pbkdf2_sha256$i=<iters>$salt=<b64>$dk=<b64>
_SCRYPT_RE = re.compile(
    r"^\$scrypt\$N=(?P<N>\d+)\$r=(?P<r>\d+)\$p=(?P<p>\d+)\$salt=(?P<salt>[A-Za-z0-9+/=]+)\$dk=(?P<dk>[A-Za-z0-9+/=]+)$"
)
_PBKDF2_RE = re.compile(r"^\$pbkdf2_sha256\$i=(?P<i>\d+)\$salt=(?P<salt>[A-Za-z0-9+/=]+)\$dk=(?P<dk>[A-Za-z0-9+/=]+)$")
