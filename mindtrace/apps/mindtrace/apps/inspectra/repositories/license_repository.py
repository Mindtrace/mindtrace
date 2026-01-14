"""Repository for license CRUD operations using mindtrace.database ODM."""

from datetime import datetime
from typing import Optional

from mindtrace.database import DocumentNotFoundError

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models.documents import LicenseDocument
from mindtrace.apps.inspectra.models.license import (
    LicenseResponse,
    LicenseStatus,
)
from mindtrace.apps.inspectra.core.license_validator import LicenseValidator
from mindtrace.apps.inspectra.core.machine_id import get_machine_id


class LicenseRepository:
    """Repository for managing licenses via MongoMindtraceODM."""

    def _to_response(self, doc: LicenseDocument) -> LicenseResponse:
        """Convert LicenseDocument to LicenseResponse with computed status."""
        now = datetime.utcnow()
        days_remaining = max(0, (doc.expires_at - now).days)

        # Determine status dynamically
        if not doc.is_active:
            status = LicenseStatus.NOT_ACTIVATED
        elif now > doc.expires_at:
            status = LicenseStatus.EXPIRED
        elif doc.machine_id != get_machine_id():
            status = LicenseStatus.HARDWARE_MISMATCH
        else:
            status = LicenseStatus.VALID

        return LicenseResponse(
            id=str(doc.id),
            license_key=doc.license_key,
            license_type=doc.license_type,
            machine_id=doc.machine_id,
            issued_at=doc.issued_at,
            expires_at=doc.expires_at,
            features=doc.features,
            max_users=doc.max_users,
            max_plants=doc.max_plants,
            max_lines=doc.max_lines,
            is_active=doc.is_active,
            status=status,
            days_remaining=days_remaining,
        )

    async def get_active_license(self) -> Optional[LicenseResponse]:
        """Get the current active license."""
        licenses = await LicenseDocument.find({"is_active": True}).to_list()
        if not licenses:
            return None
        return self._to_response(licenses[0])

    async def activate_license(self, license_content: str) -> Optional[LicenseResponse]:
        """
        Activate a license from file content.

        Validates and stores the license.
        """
        db = get_db()

        # Validate the license
        validation = LicenseValidator.validate(license_content)
        if not validation.is_valid:
            return None

        # Parse to get full details
        signed_license = LicenseValidator.parse_license_file(license_content)
        if not signed_license:
            return None

        payload = signed_license.payload
        machine_id = get_machine_id()

        # Deactivate any existing licenses
        all_licenses = await db.license.all()
        for lic in all_licenses:
            if lic.is_active:
                lic.is_active = False
                await db.license.update(lic)

        # Store new license
        license_doc = LicenseDocument(
            license_key=payload.license_key,
            license_type=payload.license_type,
            machine_id=machine_id,
            issued_at=datetime.fromisoformat(payload.issued_at),
            expires_at=datetime.fromisoformat(payload.expires_at),
            features=payload.features,
            max_users=payload.max_users,
            max_plants=payload.max_plants,
            max_lines=payload.max_lines,
            signature=signed_license.signature,
            is_active=True,
        )

        license_doc = await db.license.insert(license_doc)
        return self._to_response(license_doc)

    async def deactivate_license(self, license_id: str) -> bool:
        """Deactivate a license."""
        db = get_db()
        try:
            license_doc = await db.license.get(license_id)
            license_doc.is_active = False
            await db.license.update(license_doc)
            return True
        except DocumentNotFoundError:
            return False
        except Exception:
            return False
