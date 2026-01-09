"""Unit tests for license validation and machine ID generation."""

import base64
import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from mindtrace.apps.inspectra.core.license_validator import LicenseValidator
from mindtrace.apps.inspectra.core.machine_id import get_machine_id
from mindtrace.apps.inspectra.models.license import (
    LicenseFile,
    LicenseStatus,
    SignedLicenseFile,
)


class TestMachineId:
    """
    Unit tests for machine ID generation.

    Tests validate:
    - Machine ID is a valid SHA-256 hex string
    - Machine ID is consistent across calls
    """

    def test_machine_id_format(self):
        """Machine ID should be a 64-character hex string (SHA-256)."""
        machine_id = get_machine_id()

        assert isinstance(machine_id, str)
        assert len(machine_id) == 64
        # Should be valid hex
        int(machine_id, 16)

    def test_machine_id_consistent(self):
        """Machine ID should be consistent across multiple calls."""
        id1 = get_machine_id()
        id2 = get_machine_id()

        assert id1 == id2

    def test_machine_id_not_empty(self):
        """Machine ID should not be empty or null."""
        machine_id = get_machine_id()

        assert machine_id is not None
        assert len(machine_id) > 0


class TestLicenseValidator:
    """
    Unit tests for LicenseValidator.

    Tests validate:
    - License signing and signature validation
    - License file parsing
    - Complete license validation (signature, machine ID, expiration)
    - License file creation
    """

    @pytest.fixture
    def valid_payload(self):
        """Create a valid license payload for testing."""
        return LicenseFile(
            license_key="TEST-LICENSE-KEY",
            license_type="standard",
            issued_at=datetime.utcnow().isoformat(),
            expires_at=(datetime.utcnow() + timedelta(days=30)).isoformat(),
            features=["feature1", "feature2"],
            max_users=10,
            max_plants=5,
            max_lines=20,
            allowed_machine_ids=[get_machine_id()],
        )

    @pytest.fixture
    def expired_payload(self):
        """Create an expired license payload for testing."""
        return LicenseFile(
            license_key="EXPIRED-LICENSE",
            license_type="standard",
            issued_at=(datetime.utcnow() - timedelta(days=60)).isoformat(),
            expires_at=(datetime.utcnow() - timedelta(days=1)).isoformat(),
            features=["feature1"],
            max_users=10,
            max_plants=5,
            max_lines=20,
            allowed_machine_ids=[get_machine_id()],
        )

    @pytest.fixture
    def wrong_machine_payload(self):
        """Create a license payload bound to wrong machine."""
        return LicenseFile(
            license_key="WRONG-MACHINE",
            license_type="standard",
            issued_at=datetime.utcnow().isoformat(),
            expires_at=(datetime.utcnow() + timedelta(days=30)).isoformat(),
            features=["feature1"],
            max_users=10,
            max_plants=5,
            max_lines=20,
            allowed_machine_ids=["wrong-machine-id-123456"],
        )

    def test_sign_license(self, valid_payload):
        """Signing a license should return a hex string signature."""
        signature = LicenseValidator.sign_license(valid_payload)

        assert isinstance(signature, str)
        assert len(signature) == 64  # HMAC-SHA256 produces 64 hex chars
        int(signature, 16)  # Should be valid hex

    def test_validate_signature_valid(self, valid_payload):
        """Valid signature should pass validation."""
        signature = LicenseValidator.sign_license(valid_payload)

        result = LicenseValidator.validate_signature(valid_payload, signature)

        assert result is True

    def test_validate_signature_invalid(self, valid_payload):
        """Tampered signature should fail validation."""
        signature = LicenseValidator.sign_license(valid_payload)
        tampered_signature = "0" * 64  # Invalid signature

        result = LicenseValidator.validate_signature(valid_payload, tampered_signature)

        assert result is False

    def test_validate_signature_modified_payload(self, valid_payload):
        """Signature should fail if payload is modified after signing."""
        signature = LicenseValidator.sign_license(valid_payload)

        # Modify the payload after signing
        modified_payload = LicenseFile(
            license_key=valid_payload.license_key,
            license_type=valid_payload.license_type,
            issued_at=valid_payload.issued_at,
            expires_at=valid_payload.expires_at,
            features=valid_payload.features,
            max_users=9999,  # Modified
            max_plants=valid_payload.max_plants,
            max_lines=valid_payload.max_lines,
            allowed_machine_ids=valid_payload.allowed_machine_ids,
        )

        result = LicenseValidator.validate_signature(modified_payload, signature)

        assert result is False

    def test_parse_license_file_valid(self, valid_payload):
        """Valid base64 license file should parse correctly."""
        signature = LicenseValidator.sign_license(valid_payload)
        signed_data = {
            "payload": valid_payload.model_dump(),
            "signature": signature,
        }
        license_content = base64.b64encode(json.dumps(signed_data).encode()).decode()

        result = LicenseValidator.parse_license_file(license_content)

        assert result is not None
        assert isinstance(result, SignedLicenseFile)
        assert result.payload.license_key == valid_payload.license_key
        assert result.signature == signature

    def test_parse_license_file_invalid_base64(self):
        """Invalid base64 should return None."""
        result = LicenseValidator.parse_license_file("not-valid-base64!!!")

        assert result is None

    def test_parse_license_file_invalid_json(self):
        """Invalid JSON after decoding should return None."""
        invalid_content = base64.b64encode(b"not json").decode()

        result = LicenseValidator.parse_license_file(invalid_content)

        assert result is None

    def test_parse_license_file_missing_fields(self):
        """JSON without required fields should return None."""
        incomplete_data = {"payload": {"license_key": "test"}}  # Missing fields
        license_content = base64.b64encode(json.dumps(incomplete_data).encode()).decode()

        result = LicenseValidator.parse_license_file(license_content)

        assert result is None

    def test_validate_valid_license(self, valid_payload):
        """Valid license should pass all validation checks."""
        license_file = LicenseValidator.create_license_file(
            license_key=valid_payload.license_key,
            license_type=valid_payload.license_type,
            expires_at=datetime.utcnow() + timedelta(days=30),
            features=valid_payload.features,
            max_users=valid_payload.max_users,
            max_plants=valid_payload.max_plants,
            max_lines=valid_payload.max_lines,
            allowed_machine_ids=valid_payload.allowed_machine_ids,
        )

        result = LicenseValidator.validate(license_file)

        assert result.is_valid is True
        assert result.status == LicenseStatus.VALID
        assert result.message == "License is valid"
        assert result.days_remaining is not None
        assert result.days_remaining >= 29

    def test_validate_invalid_signature(self, valid_payload):
        """License with invalid signature should fail."""
        signed_data = {
            "payload": valid_payload.model_dump(),
            "signature": "invalid-signature-" + "0" * 40,
        }
        license_content = base64.b64encode(json.dumps(signed_data).encode()).decode()

        result = LicenseValidator.validate(license_content)

        assert result.is_valid is False
        assert result.status == LicenseStatus.INVALID_SIGNATURE
        assert "invalid" in result.message.lower()

    def test_validate_unparseable_license(self):
        """Completely invalid license content should fail."""
        result = LicenseValidator.validate("garbage-content")

        assert result.is_valid is False
        assert result.status == LicenseStatus.INVALID_SIGNATURE
        assert "parse" in result.message.lower()

    def test_validate_expired_license(self, expired_payload):
        """Expired license should fail with expired status."""
        signature = LicenseValidator.sign_license(expired_payload)
        signed_data = {
            "payload": expired_payload.model_dump(),
            "signature": signature,
        }
        license_content = base64.b64encode(json.dumps(signed_data).encode()).decode()

        result = LicenseValidator.validate(license_content)

        assert result.is_valid is False
        assert result.status == LicenseStatus.EXPIRED
        assert result.days_remaining == 0

    def test_validate_wrong_machine(self, wrong_machine_payload):
        """License bound to different machine should fail."""
        signature = LicenseValidator.sign_license(wrong_machine_payload)
        signed_data = {
            "payload": wrong_machine_payload.model_dump(),
            "signature": signature,
        }
        license_content = base64.b64encode(json.dumps(signed_data).encode()).decode()

        result = LicenseValidator.validate(license_content)

        assert result.is_valid is False
        assert result.status == LicenseStatus.HARDWARE_MISMATCH
        assert "machine" in result.message.lower()

    def test_create_license_file(self):
        """create_license_file should produce a valid, parseable license."""
        expires_at = datetime.utcnow() + timedelta(days=90)
        machine_id = get_machine_id()

        license_content = LicenseValidator.create_license_file(
            license_key="NEW-LICENSE-123",
            license_type="enterprise",
            expires_at=expires_at,
            features=["feature1", "feature2", "feature3"],
            max_users=100,
            max_plants=50,
            max_lines=200,
            allowed_machine_ids=[machine_id],
        )

        # Should be base64 encoded
        assert isinstance(license_content, str)

        # Should be parseable
        parsed = LicenseValidator.parse_license_file(license_content)
        assert parsed is not None
        assert parsed.payload.license_key == "NEW-LICENSE-123"
        assert parsed.payload.license_type == "enterprise"
        assert parsed.payload.max_users == 100
        assert machine_id in parsed.payload.allowed_machine_ids

        # Should be valid
        result = LicenseValidator.validate(license_content)
        assert result.is_valid is True

    def test_create_license_file_multiple_machines(self):
        """License can be bound to multiple machine IDs."""
        expires_at = datetime.utcnow() + timedelta(days=30)
        current_machine = get_machine_id()
        other_machine = "other-machine-id-12345"

        license_content = LicenseValidator.create_license_file(
            license_key="MULTI-MACHINE",
            license_type="standard",
            expires_at=expires_at,
            features=["feature1"],
            max_users=10,
            max_plants=5,
            max_lines=20,
            allowed_machine_ids=[current_machine, other_machine],
        )

        parsed = LicenseValidator.parse_license_file(license_content)
        assert len(parsed.payload.allowed_machine_ids) == 2

        # Should still validate (current machine is in list)
        result = LicenseValidator.validate(license_content)
        assert result.is_valid is True

    def test_license_features_returned_on_valid(self, valid_payload):
        """Valid license should return enabled features."""
        license_file = LicenseValidator.create_license_file(
            license_key=valid_payload.license_key,
            license_type=valid_payload.license_type,
            expires_at=datetime.utcnow() + timedelta(days=30),
            features=["advanced_analytics", "custom_reports", "api_access"],
            max_users=valid_payload.max_users,
            max_plants=valid_payload.max_plants,
            max_lines=valid_payload.max_lines,
            allowed_machine_ids=valid_payload.allowed_machine_ids,
        )

        result = LicenseValidator.validate(license_file)

        assert result.is_valid is True
        assert "advanced_analytics" in result.features
        assert "custom_reports" in result.features
        assert "api_access" in result.features

    def test_license_days_remaining_calculation(self):
        """days_remaining should be calculated correctly."""
        machine_id = get_machine_id()

        # License expiring in 10 days
        license_content = LicenseValidator.create_license_file(
            license_key="TEN-DAYS",
            license_type="standard",
            expires_at=datetime.utcnow() + timedelta(days=10),
            features=[],
            max_users=10,
            max_plants=5,
            max_lines=20,
            allowed_machine_ids=[machine_id],
        )

        result = LicenseValidator.validate(license_content)

        assert result.is_valid is True
        # Should be approximately 9-10 days (depending on timing)
        assert 9 <= result.days_remaining <= 10


class TestLicenseValidatorWithMockedSecret:
    """Tests that verify behavior with different license secrets."""

    def test_different_secrets_produce_different_signatures(self):
        """Same payload with different secrets should have different signatures."""
        payload = LicenseFile(
            license_key="TEST",
            license_type="standard",
            issued_at=datetime.utcnow().isoformat(),
            expires_at=(datetime.utcnow() + timedelta(days=30)).isoformat(),
            features=[],
            max_users=10,
            max_plants=5,
            max_lines=20,
            allowed_machine_ids=["test-machine"],
        )

        # Get signature with default secret
        sig1 = LicenseValidator.sign_license(payload)

        # Mock a different secret
        with patch.object(
            LicenseValidator, "get_license_secret", return_value="different-secret"
        ):
            sig2 = LicenseValidator.sign_license(payload)

        assert sig1 != sig2

    def test_signature_fails_with_wrong_secret(self):
        """License signed with one secret should fail with different secret."""
        payload = LicenseFile(
            license_key="TEST",
            license_type="standard",
            issued_at=datetime.utcnow().isoformat(),
            expires_at=(datetime.utcnow() + timedelta(days=30)).isoformat(),
            features=[],
            max_users=10,
            max_plants=5,
            max_lines=20,
            allowed_machine_ids=[get_machine_id()],
        )

        # Sign with default secret
        signature = LicenseValidator.sign_license(payload)

        # Verify with different secret should fail
        with patch.object(
            LicenseValidator, "get_license_secret", return_value="different-secret"
        ):
            result = LicenseValidator.validate_signature(payload, signature)

        assert result is False
