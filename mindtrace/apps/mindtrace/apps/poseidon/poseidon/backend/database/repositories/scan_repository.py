from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from beanie import PydanticObjectId
import asyncio

from poseidon.backend.database.init import initialize_database
from poseidon.backend.database.models.scan import Scan
from poseidon.backend.database.models.scan_image import ScanImage
from poseidon.backend.database.models.scan_classification import ScanClassification
from poseidon.backend.database.models.enums import ScanStatus
from poseidon.backend.cloud.gcs import presign_url

class ScanRepository:
    # ----------------- init -----------------
    @staticmethod
    async def _ensure_init():
        await initialize_database()

    # ----------------- CRUD -----------------
    @staticmethod
    async def create(scan_data: dict) -> Scan:
        await ScanRepository._ensure_init()
        doc = Scan(**scan_data)
        return await doc.insert()

    @staticmethod
    async def get_by_id(scan_id: str | PydanticObjectId) -> Optional[Scan]:
        await ScanRepository._ensure_init()
        try:
            return await Scan.get(scan_id, fetch_links=True)
        except Exception:
            return None

    @staticmethod
    async def get_by_serial_number(serial_number: str) -> Optional[Scan]:
        await ScanRepository._ensure_init()
        return await Scan.find_one(Scan.serial_number == serial_number)

    @staticmethod
    async def get_all() -> List[Scan]:
        await ScanRepository._ensure_init()
        return await Scan.find_all().to_list()

    @staticmethod
    async def update(scan_id: str | PydanticObjectId, update_data: dict) -> Optional[Scan]:
        await ScanRepository._ensure_init()
        try:
            doc = await Scan.get(scan_id)
            if not doc:
                return None
            for k, v in update_data.items():
                if hasattr(doc, k):
                    setattr(doc, k, v)
            await doc.save()
            return doc
        except Exception:
            return None

    @staticmethod
    async def delete(scan_id: str | PydanticObjectId) -> bool:
        await ScanRepository._ensure_init()
        try:
            doc = await Scan.get(scan_id)
            if not doc:
                return False
            await doc.delete()
            return True
        except Exception:
            return False

    # ----------------- Common filters -----------------
    @staticmethod
    async def get_by_organization(org_id: str) -> List[Scan]:
        await ScanRepository._ensure_init()
        return await Scan.find(Scan.organization.id == org_id).to_list()

    @staticmethod
    async def get_by_project(project_id: str) -> List[Scan]:
        await ScanRepository._ensure_init()
        return await Scan.find(Scan.project.id == project_id).to_list()

    @staticmethod
    async def get_by_status(status: ScanStatus) -> List[Scan]:
        await ScanRepository._ensure_init()
        return await Scan.find(Scan.status == status).to_list()

    @staticmethod
    async def get_by_user(user_id: str) -> List[Scan]:
        await ScanRepository._ensure_init()
        return await Scan.find(Scan.user.id == user_id).to_list()

    @staticmethod
    async def update_status(scan_id: str | PydanticObjectId, status: ScanStatus) -> Optional[Scan]:
        await ScanRepository._ensure_init()
        return await ScanRepository.update(scan_id, {"status": status})

    @staticmethod
    async def update_results(
        scan_id: str | PydanticObjectId,
        cls_result: str,
        cls_confidence: Optional[float] = None,
        cls_pred_time: Optional[float] = None,
    ) -> Optional[Scan]:
        await ScanRepository._ensure_init()
        payload: Dict[str, Any] = {
            "cls_result": cls_result,
            "status": ScanStatus.COMPLETED,
        }
        if cls_confidence is not None:
            payload["cls_confidence"] = cls_confidence
        if cls_pred_time is not None:
            payload["cls_pred_time"] = cls_pred_time
        return await ScanRepository.update(scan_id, payload)

    @staticmethod
    async def get_completed_scans() -> List[Scan]:
        await ScanRepository._ensure_init()
        return await Scan.find(Scan.status == ScanStatus.COMPLETED).to_list()

    @staticmethod
    async def get_failed_scans() -> List[Scan]:
        await ScanRepository._ensure_init()
        return await Scan.find(Scan.status == ScanStatus.FAILED).to_list()

    # ----------------- Helpers for grid shaping -----------------
    @staticmethod
    async def _infer_result(scan: Scan) -> str:
        """Use scan.cls_result if provided, else infer from images/classifications."""
        if scan.cls_result:
            val = str(scan.cls_result).strip().lower()
            if val == "healthy":
                return "Healthy"
            if val == "defective":
                return "Defective"
            return "Defective"

        try:
            any_img = await ScanImage.find(
                (ScanImage.scan.id == scan.id) & (ScanImage.classifications != [])
            ).first_or_none()
            return "Defective" if any_img else "Healthy"
        except Exception:
            return "Healthy"

    @staticmethod
    def _format_dt(dt: datetime) -> str:
        return dt.strftime("%a %b %d %Y %H:%M:%S")

    @staticmethod
    def _format_date(date: datetime) -> str:
        # Day + date only (e.g., "Thu Jun 26 2025")
        return date.strftime("%a %b %d %Y")

    @staticmethod
    def _to_image_url(img: Any) -> str:
        """
        Always build a presigned GCS URL from full_path.
        """
        if img is None:
            return ""

        get = img.get if isinstance(img, dict) else (lambda k, d=None: getattr(img, k, d))

        full_path = get("full_path")
        if not full_path:
            return ""

        return presign_url(full_path)

    