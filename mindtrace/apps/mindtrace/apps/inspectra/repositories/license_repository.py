"""Repository for license CRUD operations."""

import inspect
from datetime import datetime
from typing import Any, Optional

from bson import ObjectId

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models.license import (
    LicenseResponse,
    LicenseStatus,
)
from mindtrace.apps.inspectra.core.license_validator import LicenseValidator
from mindtrace.apps.inspectra.core.machine_id import get_machine_id


class LicenseRepository:
    """Repository for managing licenses in MongoDB."""

    def __init__(self):
        self._collection_name = "licenses"

    def _collection(self):
        db = get_db()
        return db[self._collection_name]

    async def _maybe_await(self, value: Any) -> Any:
        return await value if inspect.isawaitable(value) else value

    def _to_model(self, doc: dict) -> LicenseResponse:
        """Convert MongoDB document to LicenseResponse."""
        expires_at = doc["expires_at"]
        now = datetime.utcnow()
        days_remaining = max(0, (expires_at - now).days)

        # Determine status
        if not doc.get("is_active", True):
            status = LicenseStatus.NOT_ACTIVATED
        elif now > expires_at:
            status = LicenseStatus.EXPIRED
        elif doc.get("machine_id") != get_machine_id():
            status = LicenseStatus.HARDWARE_MISMATCH
        else:
            status = LicenseStatus.VALID

        return LicenseResponse(
            id=str(doc["_id"]),
            license_key=doc["license_key"],
            license_type=doc["license_type"],
            machine_id=doc["machine_id"],
            issued_at=doc["issued_at"],
            expires_at=expires_at,
            features=doc.get("features", []),
            max_users=doc.get("max_users", 0),
            max_plants=doc.get("max_plants", 0),
            max_lines=doc.get("max_lines", 0),
            is_active=doc.get("is_active", True),
            status=status,
            days_remaining=days_remaining,
        )

    async def get_active_license(self) -> Optional[LicenseResponse]:
        """Get the current active license."""
        doc = await self._maybe_await(
            self._collection().find_one({"is_active": True})
        )
        if not doc:
            return None
        return self._to_model(doc)

    async def activate_license(self, license_content: str) -> Optional[LicenseResponse]:
        """
        Activate a license from file content.

        Validates and stores the license.
        """
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
        await self._maybe_await(
            self._collection().update_many({}, {"$set": {"is_active": False}})
        )

        # Store new license
        data = {
            "license_key": payload.license_key,
            "license_type": payload.license_type,
            "machine_id": machine_id,
            "issued_at": datetime.fromisoformat(payload.issued_at),
            "expires_at": datetime.fromisoformat(payload.expires_at),
            "features": payload.features,
            "max_users": payload.max_users,
            "max_plants": payload.max_plants,
            "max_lines": payload.max_lines,
            "signature": signed_license.signature,
            "is_active": True,
        }

        result = await self._maybe_await(self._collection().insert_one(data))
        data["_id"] = result.inserted_id
        return self._to_model(data)

    async def deactivate_license(self, license_id: str) -> bool:
        """Deactivate a license."""
        try:
            oid = ObjectId(license_id)
        except Exception:
            return False

        result = await self._maybe_await(
            self._collection().update_one({"_id": oid}, {"$set": {"is_active": False}})
        )
        return result.modified_count > 0
