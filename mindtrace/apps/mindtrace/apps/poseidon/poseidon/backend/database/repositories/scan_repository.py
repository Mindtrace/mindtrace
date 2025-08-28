from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from beanie import PydanticObjectId

from poseidon.backend.database.init import initialize_database
from poseidon.backend.database.models.scan import Scan
from poseidon.backend.database.models.scan_image import ScanImage
from poseidon.backend.database.models.scan_classification import ScanClassification
from poseidon.backend.database.models.enums import ScanStatus


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

    @staticmethod
    async def list_paginated(page: int = 1, page_size: int = 10) -> List[Scan]:
        """Generic pagination without extra filters."""
        await ScanRepository._ensure_init()
        skip = max(0, (page - 1) * page_size)
        return await Scan.find_all().skip(skip).limit(page_size).to_list()

    # ----------------- Helpers for grid shaping -----------------
    @staticmethod
    async def _infer_result(scan: Scan) -> str:
        """
        Prefer scan.cls_result if present.
        Otherwise: 'Defective' if any classification exists on any image of the scan, else 'Healthy'.
        """
        if scan.cls_result:
            val = str(scan.cls_result).strip().lower()
            if val == "healthy":
                return "Healthy"
            if val == "defective":
                return "Defective"
            # Any non-empty custom label -> normalize to 'Defective' (tweak if you track multiple classes)
            return "Defective"

        # Fallback by existence of classifications
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
    async def _parts_for_scan(scan: Scan) -> Dict[str, str]:
        """Build parts dict from scan images and their classifications."""
        parts: Dict[str, str] = {}

        await scan.fetch_link(Scan.images)

        for idx, img in enumerate(scan.images, start=1):
            part_key = f"part{idx}"

            await img.fetch_link(ScanImage.classifications)

            if not img.classifications:
                parts[part_key] = "Healthy"
            else:
                labels = [cls.name for cls in img.classifications if cls.name]
                parts[part_key] = ", ".join(labels) if labels else "Defective"
        return parts

    # ----------------- Grid search for 4 columns -----------------
    @staticmethod
    async def search_grid(
        *,
        q: Optional[str] = None,
        result: str = "All",
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        page: int = 1,
        page_size: int = 10,
    ) -> Tuple[List[Dict[str, Any]], int, List[Dict[str, str]]]:
        """
        Shape scans into rows with exactly:
        - serial_number (Scan.serial_number)
        - part          (Scan.project.name)
        - created_at    (Scan.created_at -> formatted)
        - result        (Scan.cls_result or inferred via images/classifications)
        - parts         (dict from images/classifications, already materialized)
        Returns (rows, total, columns).
        """
        await ScanRepository._ensure_init()

        filter_expr: Dict[str, Any] = {}
        if q:
            filter_expr["serial_number"] = {"$regex": q, "$options": "i"}

        cursor = Scan.find(filter_expr)

        sortable_db = {
            "serial_number": Scan.serial_number,
            "created_at": Scan.created_at,
        }
        if sort_by in sortable_db:
            field = sortable_db[sort_by]
            cursor = cursor.sort(-field if sort_dir == "desc" else field)

        skip = max(0, (page - 1) * page_size)
        scans: List[Scan] = await cursor.skip(skip).limit(page_size).to_list()

        rows = []
        for s in scans:
            await s.fetch_link(Scan.project)
            part_name = getattr(s.project, "name", "-") if getattr(s, "project", None) else "-"
            res = await ScanRepository._infer_result(s)
            parts = await ScanRepository._parts_for_scan(s)

            rows.append(
                {
                    "serial_number": s.serial_number,
                    "part": part_name,
                    "created_at": ScanRepository._format_dt(s.created_at),
                    "result": res,
                    "parts": parts,
                }
            )

        if result and result != "All":
            wanted = result.strip().lower()
            rows = [r for r in rows if r["result"].lower() == wanted]

        if sort_by in ("part", "result"):
            rows.sort(key=lambda r: r[sort_by].lower(), reverse=(sort_dir == "desc"))

        if result and result != "All":
            all_scans = await Scan.find(filter_expr).to_list()
            total = 0
            for s in all_scans:
                res = await ScanRepository._infer_result(s)
                if res.lower() == wanted:
                    total += 1
        else:
            total = await Scan.find(filter_expr).count()

        columns = [
            {"id": "serial_number", "header": "Serial Number"},
            {"id": "part",          "header": "Part"},
            {"id": "created_at",    "header": "Created At"},
            {"id": "result",        "header": "Result"},
        ]

        return rows, total, columns
