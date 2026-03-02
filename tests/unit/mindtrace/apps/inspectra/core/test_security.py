"""Unit tests for Inspectra core security (password hashing, JWT, dependencies)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from mindtrace.apps.inspectra.core.security import (
    TokenData,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    decode_token,
    hash_password,
    validate_password_strength,
    verify_password,
)


def _fake_config(
    jwt_secret: str = "test-secret-at-least-32-bytes-for-hs256",
    jwt_expires_in: int = 900,
    refresh_expires_in: int = 604800,
    password_min_length: int = 12,
    pbkdf2_iterations: int = 1000,
):
    """Build a fake INSPECTRA config for patching get_inspectra_config."""
    inspectra = SimpleNamespace(
        JWT_SECRET=SecretStr(jwt_secret) if isinstance(jwt_secret, str) else jwt_secret,
        JWT_ALGORITHM="HS256",
        JWT_EXPIRES_IN=jwt_expires_in,
        REFRESH_TOKEN_EXPIRES_IN=refresh_expires_in,
        PASSWORD_MIN_LENGTH=password_min_length,
        PBKDF2_ITERATIONS=pbkdf2_iterations,
    )
    config = SimpleNamespace(INSPECTRA=inspectra)
    return config


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_validate_password_strength_valid(mock_config):
    mock_config.return_value = _fake_config()
    assert validate_password_strength("ValidPass12!") == []
    assert validate_password_strength("Abcd1234!@#x") == []


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_validate_password_strength_too_short(mock_config):
    mock_config.return_value = _fake_config(password_min_length=8)
    errs = validate_password_strength("Short1!")
    assert any("at least 8" in e for e in errs)


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_validate_password_strength_no_uppercase(mock_config):
    mock_config.return_value = _fake_config()
    errs = validate_password_strength("alllowercase1!")
    assert any("uppercase" in e.lower() for e in errs)


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_validate_password_strength_no_lowercase(mock_config):
    mock_config.return_value = _fake_config()
    errs = validate_password_strength("ALLUPPERCASE1!")
    assert any("lowercase" in e.lower() for e in errs)


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_validate_password_strength_no_digit(mock_config):
    mock_config.return_value = _fake_config()
    errs = validate_password_strength("NoDigitHere!")
    assert any("digit" in e.lower() for e in errs)


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_validate_password_strength_no_special(mock_config):
    mock_config.return_value = _fake_config()
    errs = validate_password_strength("NoSpecialChar1")
    assert any("special" in e.lower() for e in errs)


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_validate_password_strength_invalid_min_len_fallback(mock_config):
    mock_config.return_value = _fake_config()
    mock_config.return_value.INSPECTRA.PASSWORD_MIN_LENGTH = "not_an_int"
    errs = validate_password_strength("ValidPass1!")
    assert isinstance(errs, list)


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_hash_password_returns_b64_string(mock_config):
    mock_config.return_value = _fake_config(pbkdf2_iterations=100)
    out = hash_password("secret")
    assert isinstance(out, str)
    assert len(out) > 0


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_verify_password_match(mock_config):
    mock_config.return_value = _fake_config(pbkdf2_iterations=100)
    stored = hash_password("secret")
    assert verify_password("secret", stored) is True


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_verify_password_wrong_password(mock_config):
    mock_config.return_value = _fake_config(pbkdf2_iterations=100)
    stored = hash_password("secret")
    assert verify_password("wrong", stored) is False


def test_verify_password_none_returns_false():
    assert verify_password("x", None) is False


def test_verify_password_empty_string_returns_false():
    assert verify_password("x", "") is False


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_verify_password_invalid_b64_returns_false(mock_config):
    mock_config.return_value = _fake_config()
    assert verify_password("x", "not-valid-base64!!!") is False


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_verify_password_hash_too_short_returns_false(mock_config):
    import base64

    mock_config.return_value = _fake_config()
    # Decode to 16 bytes (salt only); verify_password requires salt + key
    short = base64.b64encode(bytes(16)).decode("ascii")
    assert verify_password("x", short) is False


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_create_and_decode_access_token(mock_config):
    mock_config.return_value = _fake_config()
    token = create_access_token("user-123")
    assert isinstance(token, str)
    data = decode_token(token)
    assert data.sub == "user-123"
    assert data.type is None


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_create_and_decode_refresh_token(mock_config):
    mock_config.return_value = _fake_config()
    token = create_refresh_token("user-456")
    assert isinstance(token, str)
    data = decode_refresh_token(token)
    assert data.sub == "user-456"
    assert data.type == "refresh"


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_decode_token_expired_raises(mock_config):
    mock_config.return_value = _fake_config(jwt_expires_in=-10)
    token = create_access_token("user")
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_decode_token_invalid_raises(mock_config):
    mock_config.return_value = _fake_config()
    with pytest.raises(HTTPException) as exc_info:
        decode_token("invalid.jwt.here")
    assert exc_info.value.status_code == 401
    assert "invalid" in exc_info.value.detail.lower()


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_decode_refresh_token_access_token_raises(mock_config):
    mock_config.return_value = _fake_config()
    access = create_access_token("user")
    with pytest.raises(HTTPException) as exc_info:
        decode_refresh_token(access)
    assert exc_info.value.status_code == 401
    assert "refresh" in exc_info.value.detail.lower()


def test_token_data_model():
    data = TokenData(sub="id", iat=1000, exp=2000, type="refresh")
    assert data.sub == "id"
    assert data.type == "refresh"


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
def test_get_jwt_secret_returns_empty_when_none(mock_config):
    """_get_jwt_secret returns '' when JWT_SECRET is None."""
    from mindtrace.apps.inspectra.core.security import _get_jwt_secret  # noqa: PLC2701

    cfg = _fake_config()
    cfg.INSPECTRA.JWT_SECRET = None
    assert _get_jwt_secret(cfg.INSPECTRA) == ""


def test_get_jwt_secret_returns_plain_str_when_not_secret_str():
    """_get_jwt_secret returns str(v) when JWT_SECRET is plain str (no get_secret_value)."""
    from mindtrace.apps.inspectra.core.security import _get_jwt_secret  # noqa: PLC2701

    cfg = _fake_config()
    cfg.INSPECTRA.JWT_SECRET = "plain-secret-string"
    assert _get_jwt_secret(cfg.INSPECTRA) == "plain-secret-string"


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
@pytest.mark.asyncio
async def test_require_user_raises_401_when_no_credentials(mock_config):
    """require_user raises 401 when credentials is None."""
    from mindtrace.apps.inspectra.core.security import require_user

    mock_config.return_value = _fake_config()
    with pytest.raises(HTTPException) as exc_info:
        await require_user(credentials=None)
    assert exc_info.value.status_code == 401
    assert "Authorization" in exc_info.value.detail


@patch("mindtrace.apps.inspectra.core.security.get_inspectra_config")
@pytest.mark.asyncio
async def test_require_user_returns_token_data_when_valid(mock_config):
    """require_user decodes token and returns TokenData when credentials provided."""
    from fastapi.security import HTTPAuthorizationCredentials

    from mindtrace.apps.inspectra.core.security import require_user

    mock_config.return_value = _fake_config()
    token = create_access_token("user-99")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    result = await require_user(credentials=creds)
    assert result.sub == "user-99"
    assert result.type is None


@pytest.mark.asyncio
async def test_get_current_user_user_not_found_raises_401():
    """get_current_user raises 401 when user is not in DB."""
    from mindtrace.apps.inspectra.core.security import TokenData, get_current_user
    from mindtrace.database.core.exceptions import DocumentNotFoundError

    mock_odm = MagicMock()
    mock_odm.user.get = AsyncMock(side_effect=DocumentNotFoundError())
    with patch("mindtrace.apps.inspectra.db.get_odm", return_value=mock_odm):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token_data=TokenData(sub="missing-user", iat=1, exp=999))
        assert exc_info.value.status_code == 401
        assert "User not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_org_inactive_raises_403():
    """get_current_user raises 403 when org is inactive and user is not super_admin."""
    from mindtrace.apps.inspectra.core.security import TokenData, get_current_user
    from mindtrace.apps.inspectra.models import User
    from mindtrace.apps.inspectra.models.enums import OrganizationStatus, UserRole

    mock_user = MagicMock(spec=User)
    mock_user.role = UserRole.ADMIN
    mock_user.organization_id = "org-123"

    mock_org = MagicMock()
    mock_org.status = OrganizationStatus.DISABLED

    mock_odm = MagicMock()
    mock_odm.user.get = AsyncMock(return_value=mock_user)
    mock_odm.organization.get = AsyncMock(return_value=mock_org)

    with patch("mindtrace.apps.inspectra.db.get_odm", return_value=mock_odm):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token_data=TokenData(sub="user-1", iat=1, exp=999))
        assert exc_info.value.status_code == 403
        assert "inactive" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_get_current_user_super_admin_bypasses_org_inactive():
    """get_current_user returns user when org is inactive but user is super_admin (no 403)."""
    from mindtrace.apps.inspectra.core.security import TokenData, get_current_user
    from mindtrace.apps.inspectra.models import User
    from mindtrace.apps.inspectra.models.enums import OrganizationStatus, UserRole

    mock_user = MagicMock(spec=User)
    mock_user.role = UserRole.SUPER_ADMIN
    mock_user.organization_id = "org-123"

    mock_org = MagicMock()
    mock_org.status = OrganizationStatus.DISABLED

    mock_odm = MagicMock()
    mock_odm.user.get = AsyncMock(return_value=mock_user)
    mock_odm.organization.get = AsyncMock(return_value=mock_org)

    with patch("mindtrace.apps.inspectra.db.get_odm", return_value=mock_odm):
        user = await get_current_user(token_data=TokenData(sub="user-1", iat=1, exp=999))
        assert user.role == UserRole.SUPER_ADMIN


@pytest.mark.asyncio
async def test_get_current_user_no_org_id_skips_org_check():
    """get_current_user returns user when organization_id is None (no org check)."""
    from mindtrace.apps.inspectra.core.security import TokenData, get_current_user
    from mindtrace.apps.inspectra.models import User

    mock_user = MagicMock(spec=User)
    mock_user.role = "user"
    mock_user.organization_id = None

    mock_odm = MagicMock()
    mock_odm.user.get = AsyncMock(return_value=mock_user)

    with patch("mindtrace.apps.inspectra.db.get_odm", return_value=mock_odm):
        user = await get_current_user(token_data=TokenData(sub="user-1", iat=1, exp=999))
        assert user.organization_id is None


@pytest.mark.asyncio
async def test_get_current_user_reraises_http_exception():
    """get_current_user re-raises HTTPException from org check."""
    from mindtrace.apps.inspectra.core.security import TokenData, get_current_user
    from mindtrace.apps.inspectra.models import User
    from mindtrace.apps.inspectra.models.enums import UserRole

    mock_user = MagicMock(spec=User)
    mock_user.role = UserRole.ADMIN
    mock_user.organization_id = "org-123"

    mock_odm = MagicMock()
    mock_odm.user.get = AsyncMock(return_value=mock_user)
    mock_odm.organization.get = AsyncMock(side_effect=HTTPException(status_code=403, detail="Organization is inactive"))

    with patch("mindtrace.apps.inspectra.db.get_odm", return_value=mock_odm):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token_data=TokenData(sub="user-1", iat=1, exp=999))
        assert exc_info.value.status_code == 403
