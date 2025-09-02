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
    def _to_image_url(img: Any) -> str:
        """
        Prefer a fully-qualified URL if present; else construct canonical GCS path.

        Priority:
        1) image_url if http(s)/gs://                  -> passthrough
        2) full_path if http(s)/gs://                  -> passthrough
        3) bucket_name + full_path (relative)          -> gs://bucket/<full_path>
        4) bucket_name + path (+ file_name if needed)  -> gs://bucket/<path>/<file_name?>
        5) bucket_name + file_name                     -> gs://bucket/<file_name>
        6) fallback: file_name                         -> <file_name>
        """
        if img is None:
            return ""

        get = img.get if isinstance(img, dict) else (lambda k, d=None: getattr(img, k, d))

        HTTP_PREFIXES = ("http://", "https://")
        GS_PREFIX = "gs://"

        def as_str(x: Any) -> str:
            return x if isinstance(x, str) else ("" if x is None else str(x))

        def is_http(s: Any) -> bool:
            return as_str(s).startswith(HTTP_PREFIXES)

        def is_gs(s: Any) -> bool:
            return as_str(s).startswith(GS_PREFIX)

        def norm(s: Any) -> str:
            return as_str(s).replace("\\", "/").strip().strip("/")

        def join(path: Any, fname: Any) -> str:
            p, f = norm(path), norm(fname)
            if not p:
                return f
            if not f:
                return p
            return p if p.endswith(f) else f"{p}/{f}"

        # ---- logic ----
        image_url = get("image_url")
        if is_http(image_url) or is_gs(image_url):
            return as_str(image_url)

        full_path = get("full_path")
        if is_http(full_path) or is_gs(full_path):
            return as_str(full_path)

        bucket = norm(get("bucket_name"))
        path = get("path", "") or ""
        file_name = get("file_name", "") or ""

        if bucket and full_path:
            fp = norm(full_path)
            return f"{GS_PREFIX}{bucket}/{fp}" if fp else f"{GS_PREFIX}{bucket}"

        if bucket and (path or file_name):
            joined = join(path, file_name)
            return f"{GS_PREFIX}{bucket}/{joined}" if joined else f"{GS_PREFIX}{bucket}"

        return as_str(file_name)


    @staticmethod
    async def _parts_for_scan(scan: Scan) -> List[Dict[str, Any]]:
        """
        Build a list of parts from this scan's images + classifications.
        """
        parts: List[Dict[str, Any]] = []

        images: List[ScanImage] = await ScanImage.find(ScanImage.scan.id == scan.id).to_list()
        if not images:
            return parts

        sem = asyncio.Semaphore(20)

        async def _fetch_links(img: ScanImage):
            async with sem:
                await asyncio.gather(
                    img.fetch_link(ScanImage.camera),
                    img.fetch_link(ScanImage.classifications),
                    return_exceptions=True,
                )
            return img

        images = await asyncio.gather(*(_fetch_links(img) for img in images))

        for idx, img in enumerate(images, start=1):
            cam = getattr(img, "camera", None)
            if cam is not None and getattr(cam, "name", None):
                name = cam.name
            else:
                path = (getattr(img, "path", "") or "").replace("\\", "/").strip().strip("/")
                if path:
                    name = path.split("/")[-1]
                else:
                    stem = (getattr(img, "file_name", "") or "").rsplit(".", 1)[0]
                    name = stem or f"Camera_{idx}"

            classes: List[str] = []
            seen_lower = set()
            bbox_payload: Optional[Dict[str, Any]] = None
            max_conf: Optional[float] = None

            for cls in (getattr(img, "classifications", None) or []):
                label = getattr(cls, "det_cls", None) or getattr(cls, "name", None)
                if label:
                    lkey = str(label).strip().lower()
                    if lkey and lkey not in seen_lower:
                        classes.append(str(label))
                        seen_lower.add(lkey)

                # max confidence
                c = getattr(cls, "cls_confidence", None)
                if c is not None and (max_conf is None or c > max_conf):
                    max_conf = c

                # first valid bbox
                if bbox_payload is None:
                    x = getattr(cls, "det_x", None)
                    y = getattr(cls, "det_y", None)
                    w = getattr(cls, "det_w", None)
                    h = getattr(cls, "det_h", None)
                    if None not in (x, y, w, h):
                        bbox_payload = {"x": x, "y": y, "w": w, "h": h, "class": (label or "")}

            non_healthy = [c for c in classes if c.lower() != "healthy"]
            status = ", ".join(non_healthy) if non_healthy else "Healthy"

            parts.append(
                {
                    "name": name,
                    "status": status,
                    "image_url": ScanRepository._to_image_url(img),
                    "image_id": str(getattr(img, "id", "")),
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

        expr = Scan.serial_number.regex(q, "i") if q else None
        cursor = Scan.find(expr) if expr is not None else Scan.find_all()

        sortable_db = {"serial_number": Scan.serial_number, "created_at": Scan.created_at}
        if sort_by in sortable_db:
            field = sortable_db[sort_by]
            cursor = cursor.sort(-field if sort_dir == "desc" else field)

        skip = max(0, (page - 1) * page_size)
        scans: List[Scan] = await cursor.skip(skip).limit(page_size).to_list()

        if not scans:
            total = await (Scan.find(expr) if expr is not None else Scan.find_all()).count()
            columns = [
                {"id": "serial_number", "header": "Serial Number"},
                {"id": "part",          "header": "Part"},
                {"id": "created_at",    "header": "Created At"},
                {"id": "result",        "header": "Result"},
            ]
            return [], total, columns

        sem = asyncio.Semaphore(20)

        async def _fetch_scan_links(s: Scan):
            async with sem:
                tasks = []
                if getattr(s, "project", None) is not None:
                    tasks.append(s.fetch_link(Scan.project))
                if getattr(s, "user", None) is not None:
                    tasks.append(s.fetch_link(Scan.user))
                if getattr(s, "model_deployment", None) is not None:
                    tasks.append(s.fetch_link(Scan.model_deployment))
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

            md = getattr(s, "model_deployment", None)
            if md is not None and getattr(md, "model", None) is not None:
                try:
                    await md.fetch_link("model")
                except Exception:
                    pass
            return s

        scans = await asyncio.gather(*(_fetch_scan_links(s) for s in scans))

        async def _row_for_scan(s: Scan) -> Dict[str, Any]:
            part_name = "-"
            proj = getattr(s, "project", None)
            if proj is not None:
                part_name = getattr(proj, "name", "-")

            operator_name = "-"
            user = getattr(s, "user", None)
            if user is not None:
                operator_name = getattr(user, "username", "-")

            model_version = "-"
            md = getattr(s, "model_deployment", None)
            if md:
                model = getattr(md, "model", None)
                mname = getattr(model, "name", "Model") if model else "Model"
                mver = getattr(model, "version", None) if model else None
                model_version = f"{mname} v{mver}" if mver is not None else mname

            confidence_str = "-"
            if getattr(s, "cls_confidence", None) is not None:
                confidence_str = f"{s.cls_confidence:.1%}"

            parts_list = await ScanRepository._parts_for_scan(s)
            res = await ScanRepository._infer_result(s)

            return {
                "id": str(s.id),
                "serial_number": s.serial_number,
                "part": part_name,
                "created_at": ScanRepository._format_date(s.created_at),
                "result": res,
                "parts": parts_list,
                "operator": operator_name,
                "model_version": model_version,
                "confidence": confidence_str,
            }

        rows = await asyncio.gather(*(_row_for_scan(s) for s in scans))

        if result and result != "All":
            wanted = result.strip().lower()
            rows = [r for r in rows if r["result"].lower() == wanted]

        if sort_by in ("part", "result"):
            rows.sort(key=lambda r: r[sort_by].lower(), reverse=(sort_dir == "desc"))

        if result and result != "All":
            wanted = result.strip().lower()
            all_scans = await (Scan.find(expr) if expr is not None else Scan.find_all()).to_list()
            total = 0
            for s in all_scans:
                res = await ScanRepository._infer_result(s)
                if res.lower() == wanted:
                    total += 1
        else:
            total = await (Scan.find(expr) if expr is not None else Scan.find_all()).count()

        columns = [
            {"id": "serial_number", "header": "Serial Number"},
            {"id": "part",          "header": "Part"},
            {"id": "created_at",    "header": "Created At"},
            {"id": "result",        "header": "Result"},
        ]

        return rows, total, columns
