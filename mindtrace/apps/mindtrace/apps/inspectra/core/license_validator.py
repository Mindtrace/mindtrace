"""License validation utilities for offline license checking."""

import base64
import hashlib
import hmac
import json
from datetime import datetime
from typing import Optional

from mindtrace.apps.inspectra.models.license import (
    LicenseFile,
    LicenseStatus,
    LicenseValidationResponse,
    SignedLicenseFile,
)

from .machine_id import get_machine_id
from .settings import get_inspectra_config


class LicenseValidator:
    """Validates license files offline using HMAC signatures."""

    @staticmethod
    def get_license_secret() -> str:
        """Get the license signing secret from config."""
        config = get_inspectra_config()
        # Get actual secret value - Config masks secrets, use get_secret() to retrieve
        secret = config.get_secret("INSPECTRA", "LICENSE_SECRET")
        if secret is None:
            secret = getattr(config.INSPECTRA, "LICENSE_SECRET", None)
        if secret is None:
            raise ValueError("LICENSE_SECRET is not configured")
        return str(secret)

    @staticmethod
    def validate_signature(payload: LicenseFile, signature: str) -> bool:
        """Validate the HMAC signature of a license file."""
        secret = LicenseValidator.get_license_secret()
        payload_json = json.dumps(payload.model_dump(), sort_keys=True)
        expected_sig = hmac.new(
            secret.encode(), payload_json.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected_sig)

    @staticmethod
    def sign_license(payload: LicenseFile) -> str:
        """Sign a license file payload. Used for generating licenses."""
        secret = LicenseValidator.get_license_secret()
        payload_json = json.dumps(payload.model_dump(), sort_keys=True)
        return hmac.new(
            secret.encode(), payload_json.encode(), hashlib.sha256
        ).hexdigest()

    @staticmethod
    def parse_license_file(license_content: str) -> Optional[SignedLicenseFile]:
        """Parse a base64-encoded license file."""
        try:
            decoded = base64.b64decode(license_content)
            data = json.loads(decoded)
            return SignedLicenseFile(
                payload=LicenseFile(**data["payload"]), signature=data["signature"]
            )
        except Exception:
            return None

    @staticmethod
    def validate(license_content: str) -> LicenseValidationResponse:
        """
        Validate a license file completely offline.

        Checks:
        1. Signature validity
        2. Machine ID binding
        3. Expiration date
        """
        # Parse license file
        signed_license = LicenseValidator.parse_license_file(license_content)
        if not signed_license:
            return LicenseValidationResponse(
                is_valid=False,
                status=LicenseStatus.INVALID_SIGNATURE,
                message="Could not parse license file",
            )

        payload = signed_license.payload
        signature = signed_license.signature

        # Validate signature
        if not LicenseValidator.validate_signature(payload, signature):
            return LicenseValidationResponse(
                is_valid=False,
                status=LicenseStatus.INVALID_SIGNATURE,
                message="License signature is invalid",
            )

        # Check machine ID
        current_machine_id = get_machine_id()
        if current_machine_id not in payload.allowed_machine_ids:
            return LicenseValidationResponse(
                is_valid=False,
                status=LicenseStatus.HARDWARE_MISMATCH,
                message="License is not valid for this machine",
            )

        # Check expiration
        expires_at = datetime.fromisoformat(payload.expires_at)
        now = datetime.utcnow()

        if now > expires_at:
            return LicenseValidationResponse(
                is_valid=False,
                status=LicenseStatus.EXPIRED,
                message="License has expired",
                days_remaining=0,
                features=payload.features,
            )

        days_remaining = (expires_at - now).days

        return LicenseValidationResponse(
            is_valid=True,
            status=LicenseStatus.VALID,
            message="License is valid",
            days_remaining=days_remaining,
            features=payload.features,
        )

    @staticmethod
    def create_license_file(
        license_key: str,
        license_type: str,
        expires_at: datetime,
        features: list,
        max_users: int,
        max_plants: int,
        max_lines: int,
        allowed_machine_ids: list,
    ) -> str:
        """
        Create a signed license file (admin/generator function).

        Returns base64-encoded signed license.
        """
        payload = LicenseFile(
            license_key=license_key,
            license_type=license_type,
            issued_at=datetime.utcnow().isoformat(),
            expires_at=expires_at.isoformat(),
            features=features,
            max_users=max_users,
            max_plants=max_plants,
            max_lines=max_lines,
            allowed_machine_ids=allowed_machine_ids,
        )

        signature = LicenseValidator.sign_license(payload)

        signed = {
            "payload": payload.model_dump(),
            "signature": signature,
        }

        return base64.b64encode(json.dumps(signed).encode()).decode()
