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

import logging, sys

logger = logging.getLogger("scan_repo")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler(stream=sys.stdout)
    _h.setLevel(logging.INFO)
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
    logger.addHandler(_h)

def _dbg(msg: str):
    # Always try both logging and a flushed print so you see it in any env
    try:
        logger.info(msg)
    except Exception:
        pass
    try:
        print(msg, flush=True)
    except Exception:
        pass

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

        pipeline = [
            # Optional filter by serial_number
            {"$match": {"serial_number": {"$regex": q, "$options": "i"}}} if q else {"$match": {}},

            # Compute 'result' from cls_result (fallback Healthy)
            {"$set": {"result": {"$ifNull": ["$cls_result", "Healthy"]}}},

            # Optional filter by result
            {"$match": {"result": result}} if result and result != "All" else {"$match": {}},

            # ---- Project -> project_name ----
            {"$addFields": {"project_id": "$project.$id"}},               # extract ObjectId from DBRef
            {"$lookup": {
                "from": "Project",
                "localField": "project_id",
                "foreignField": "_id",
                "as": "project_doc",
            }},
            {"$set": {"project_name": {"$ifNull": [{"$first": "$project_doc.name"}, "-"]}}},
            {"$unset": ["project_id", "project_doc"]},

            # ---- Images (from DBRef array 'images') ----
            {"$addFields": {
                "image_ids": {
                    "$map": {
                        "input": {"$ifNull": ["$images", []]},
                        "as": "ref",
                        "in": "$$ref.$id"                 # take the ObjectId from each DBRef
                    }
                }
            }},
            {"$lookup": {
                "from": "ScanImage",
                "localField": "image_ids",
                "foreignField": "_id",
                "as": "images",                           # replaces with full image docs array
            }},

            # ---- Classifications (by scan id) ----
            {"$lookup": {
                "from": "ScanClassification",
                "let": {"imgIds": "$image_ids"},
                "pipeline": [
                    {"$match": {"$expr": {"$in": ["$image.$id", "$$imgIds"]}}},
                ],
                "as": "classifications",
            }},

            # ---- Sort & paginate ----
            {"$sort": {"created_at": -1 if sort_dir == "desc" else 1, "_id": -1}},
            {"$skip": max(0, (page - 1) * page_size)},
            {"$limit": page_size},
        ]

        docs: List[Dict[str, Any]] = await Scan.aggregate(pipeline).to_list()

        rows: List[Dict[str, Any]] = []

        for d in docs:
            # group classifications by image id so each part can list its classes
            # clses = d.get("classifications", []) or []
            # print(clses)
            # cls_by_img = defaultdict(list)
            for c in clses:
                img_ref = c.get("image", {})
                iid = img_ref.get("$id") if isinstance(img_ref, dict) else None
                if iid is not None:
                    cls_by_img[str(iid)].append(c)

            parts = []
            # for img in (d.get("images", []) or []):
            #     img_id = str(img.get("_id"))
            #     name = (img.get("file_name") or "Camera").rsplit(".", 1)[0]

            #     classes, seen_lower = [], set()
            #     bbox_payload, max_conf = None, None
            #     for c in cls_by_img.get(img_id, []):
            #         label = c.get("det_cls") or c.get("name")
            #         if label:
            #             lkey = str(label).strip().lower()
            #             if lkey and lkey not in seen_lower:
            #                 classes.append(str(label))
            #                 seen_lower.add(lkey)
            #         conf = c.get("cls_confidence")
            #         if conf is not None and (max_conf is None or conf > max_conf):
            #             max_conf = conf
            #         if bbox_payload is None:
            #             x, y, w, h = c.get("det_x"), c.get("det_y"), c.get("det_w"), c.get("det_h")
            #             if None not in (x, y, w, h):
            #                 bbox_payload = {"x": x, "y": y, "w": w, "h": h, "class": (label or "")}

            #     # you’re already presigning server-side elsewhere; keep it here minimal
            # for p in 
            #     parts.append({
            #         "name": name,
            #         "status": ", ".join([c for c in classes if c.lower() != "healthy"]) or "Healthy",
            #         "image_url": "",  # fill with presign_url(img["full_path"]) if desired
            #         "image_id": img_id,
            #         "classes": classes,
            #         "bbox": bbox_payload,
            #         "confidence": max_conf,
            #     })
            rows.append({
                "created_at": d.get("created_at"),
                "id": str(d.get("_id")),
                "part": d.get("project_name", "-"),
                "parts": parts,
                "result": d.get("result"),
                "serial_number": d.get("serial_number"),
            })

        total = await Scan.find({} if not q else {"serial_number": {"$regex": q, "$options": "i"}}).count()

        columns = [
            {"id": "serial_number", "header": "Serial Number"},
            {"id": "created_at", "header": "Created At"},
        ]

        return rows, total, columns
