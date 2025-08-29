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
    def _to_image_url(img: ScanImage) -> str:
        """Prefer full_path; else compose from bucket/path/file."""
        if getattr(img, "full_path", None):
            return img.full_path
        bucket = getattr(img, "bucket_name", None)
        path = getattr(img, "path", "") or ""
        file_name = getattr(img, "file_name", "") or ""
        if bucket:
            # gs://bucket/path/file
            prefix = f"gs://{bucket}"
            if path:
                return f"{prefix}/{path}/{file_name}".rstrip("/")
            return f"{prefix}/{file_name}".rstrip("/")
        # last fallback: just the file name
        return file_name

    @staticmethod
    async def _parts_for_scan(scan: Scan) -> List[Dict[str, Any]]:
        """
        Build a list of parts from this scan's images + classifications.

        Each item:
        {
            "name": "...",                  # camera name or derived from path/file
            "status": "Healthy" | "Porosity, Crack",
            "image_url": "gs://.../scan_001.jpg",
            "image_id": "<ObjectId>",
            "classes": ["Healthy", "Porosity"],
            "bbox": {"x": ..., "y": ..., "w": ..., "h": ..., "class": "..."} | None,
            "confidence": 0.95 | None
        }
        """
        parts: List[Dict[str, Any]] = []

        # Get all images for this scan in one go.
        images: List[ScanImage] = await ScanImage.find(ScanImage.scan.id == scan.id).to_list()

        for idx, img in enumerate(images, start=1):
            # Load camera + classifications
            await img.fetch_link(ScanImage.camera)
            await img.fetch_link(ScanImage.classifications)

            # Name: prefer camera.name, else last path segment, else file_name, else fallback
            if getattr(img, "camera", None) and getattr(img.camera, "name", None):
                name = img.camera.name
            else:
                path = getattr(img, "path", "") or ""
                if path:
                    name = path.split("/")[-1]
                else:
                    name = (getattr(img, "file_name", "") or "").split(".")[0] or f"Camera_{idx}"

            classes: List[str] = []
            bbox_payload: Optional[Dict[str, Any]] = None
            max_conf: Optional[float] = None

            for cls in (img.classifications or []):
                # Class label
                label = cls.det_cls or cls.name
                if label:
                    if label not in classes:
                        classes.append(label)
                # Track max confidence
                if cls.cls_confidence is not None:
                    max_conf = max(max_conf or cls.cls_confidence, cls.cls_confidence)

                # First bbox (for preview)
                if (
                    bbox_payload is None
                    and cls.det_x is not None and cls.det_y is not None
                    and cls.det_w is not None and cls.det_h is not None
                ):
                    bbox_payload = {
                        "x": cls.det_x,
                        "y": cls.det_y,
                        "w": cls.det_w,
                        "h": cls.det_h,
                        "class": label or "",
                    }

            # Status: if any non-healthy classes, join them; else Healthy.
            non_healthy = [c for c in classes if c.lower() != "healthy"]
            status = ", ".join(non_healthy) if non_healthy else "Healthy"

            parts.append(
                {
                    "name": name,
                    "status": status,
                    "image_url": ScanRepository._to_image_url(img),
                    "image_id": str(img.id),
                    "classes": classes,
                    "bbox": bbox_payload,
                    "confidence": max_conf,
                }
            )

        return parts

    # ----------------- Grid search -----------------
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
        await ScanRepository._ensure_init()

        filter_expr: Dict[str, Any] = {}
        if q:
            filter_expr["serial_number"] = {"$regex": q, "$options": "i"}

        cursor = Scan.find(filter_expr)

        sortable_db = {
            "serial_number": Scan.serial_number,
            "created_at":   Scan.created_at,
        }
        if sort_by in sortable_db:
            field = sortable_db[sort_by]
            cursor = cursor.sort(-field if sort_dir == "desc" else field)

        skip = max(0, (page - 1) * page_size)
        scans: List[Scan] = await cursor.skip(skip).limit(page_size).to_list()

        rows: List[Dict[str, Any]] = []
        for s in scans:
            await s.fetch_link(Scan.project)

            part_name = getattr(s.project, "name", "-") if getattr(s, "project", None) else "-"

            # Operator
            operator_name = "-"
            if getattr(s, "user", None):
                await s.fetch_link(Scan.user)
                operator_name = getattr(s.user, "username", "-")

            # Model version (ModelDeployment -> Model)
            model_version = "-"
            if getattr(s, "model_deployment", None):
                await s.fetch_link(Scan.model_deployment)
                md = s.model_deployment
                # best-effort fetch of linked model
                if getattr(md, "model", None):
                    try:
                        await md.fetch_link("model")
                        model = md.model
                        mname = getattr(model, "name", "Model")
                        mver  = getattr(model, "version", None)
                        model_version = f"{mname} v{mver}" if mver is not None else mname
                    except Exception:
                        pass

            # Confidence (scan-level)
            confidence_str = "-"
            if s.cls_confidence is not None:
                confidence_str = f"{s.cls_confidence:.1%}"

            res = await ScanRepository._infer_result(s)
            parts_list = await ScanRepository._parts_for_scan(s)

            rows.append(
                {
                    "id": str(s.id),
                    "serial_number": s.serial_number,
                    "part": part_name,
                    "created_at": ScanRepository._format_date(s.created_at),  # day + date
                    "result": res,
                    "parts": parts_list,
                    "operator": operator_name,
                    "model_version": model_version,
                    "confidence": confidence_str,
                }
            )

        # post filters/sort
        if result and result != "All":
            wanted = result.strip().lower()
            rows = [r for r in rows if r["result"].lower() == wanted]

        if sort_by in ("part", "result"):
            rows.sort(key=lambda r: r[sort_by].lower(), reverse=(sort_dir == "desc"))

        # totals
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