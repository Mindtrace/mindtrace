from typing import Optional, List, Dict, Any, Tuple
import logging
import sys

from bson import ObjectId
from poseidon.backend.database.models.scan import Scan
from poseidon.backend.database.models.scan_image import ScanImage
from poseidon.backend.database.models.scan_classification import ScanClassification
from poseidon.backend.cloud.gcs import presign_url
from poseidon.backend.database.init import initialize_database

logger = logging.getLogger("scan_repo")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler(stream=sys.stdout)
    _h.setLevel(logging.INFO)
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
    logger.addHandler(_h)


class TableRepository:
    # ------------------------------- init ------------------------------------
    @staticmethod
    async def _ensure_init():
        await initialize_database()

    # ----------------------------- utilities ---------------------------------
    @staticmethod
    def _to_obj_id(maybe_id: Optional[str]) -> Optional[ObjectId]:
        if not maybe_id:
            return None
        try:
            return ObjectId(str(maybe_id))
        except Exception:
            return None

    # ---------------------------- parts loader --------------------------------
    @staticmethod
    async def fetch_row_parts(scan_id: str) -> List[Dict[str, Any]]:
        """Return ONE chip per classification for a scan:
        {"name": str, "status": str, "image_url": str}
        All derived by scan_id (no project fields, no fallbacks).
        """
        try:
            oid = ObjectId(str(scan_id))
        except Exception:
            return []

        img_pipeline = [
            {"$match": {"$or": [{"scan.$id": oid}, {"scan": oid}]}},
            {"$project": {"_id": 1, "full_path": 1}},
        ]
        images = await ScanImage.aggregate(img_pipeline).to_list()

        img_url_by_id = {}
        for img in images or []:
            img_id = img.get("_id")
            fp = img.get("full_path") or ""
            if img_id:
                try:
                    img_url_by_id[img_id] = presign_url(fp) if fp else ""
                except Exception:
                    img_url_by_id[img_id] = ""


        cls_pipeline = [
            {"$match": {"$or": [{"scan.$id": oid}, {"scan": oid}]}},
            {
                "$project": {
                    "name": 1,
                    "det_cls": 1,
                    "image_id": {"$ifNull": ["$image.$id", "$image"]},
                }
            },
        ]
        clss = await ScanClassification.aggregate(cls_pipeline).to_list()

        parts: List[Dict[str, Any]] = []
        for c in clss or []:
            name = (c.get("name") or "Camera")
            det = (c.get("det_cls") or "Healthy")
            image_id = c.get("image_id")
            image_url = img_url_by_id.get(image_id, "")
            parts.append({
                "name": name,
                "status": det,
                "image_url": image_url,
            })

        return parts

    # ------------------------------ grid search ------------------------------
    @staticmethod
    async def search_grid(
        *,
        q: Optional[str] = None,
        result: str = "All",
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        page: int = 1,
        page_size: int = 10,
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int, List[Dict[str, str]]]:
        """
        Returns (rows, total, columns).

        - Exact match on serial_number (uses scan_sn_asc index).
        - Optional org/project filters (by DBRef id).
        - Result filter without computing fields (Healthy = cls_result is None or "Healthy").
        - Stable sort on (created_at, _id), paginate, then minimal $lookup to get project.name
          so "part" shows the human name.
        """
        await TableRepository._ensure_init()

        def to_oid(v: Optional[str]) -> Optional[ObjectId]:
            try:
                return ObjectId(str(v)) if v else None
            except Exception:
                return None

        # ------------------- index-friendly $match ----------------------------
        match: Dict[str, Any] = {}

        # Exact serial match (fast equality on scan_sn_asc)
        if q:
            sn = str(q).strip()
            if sn:
                match["serial_number"] = sn

        # Result filter; Healthy means cls_result is None OR "Healthy"
        if result and result != "All":
            if result.lower() == "healthy":
                match["$or"] = [{"cls_result": None}, {"cls_result": "Healthy"}]
            else:
                match["cls_result"] = result

        pid = to_oid(project_id)
        if pid:
            match["project.$id"] = pid

        oid = to_oid(org_id)
        if oid:
            match["organization.$id"] = oid

        # ------------------------- sort / paging ------------------------------
        dir_num = -1 if str(sort_dir).lower() == "desc" else 1
        sort_by = sort_by if sort_by in ("created_at", "serial_number") else "created_at"
        sort_stage = {"$sort": {sort_by: dir_num, "_id": dir_num}}

        try:
            page = max(1, int(page))
        except Exception:
            page = 1
        try:
            page_size = max(1, min(100, int(page_size)))
        except Exception:
            page_size = 10
        skip_n = (page - 1) * page_size

        # --------------------------- pipeline --------------------------------
        pipeline: List[Dict[str, Any]] = []
        if match:
            pipeline.append({"$match": match})

        pipeline += [
            sort_stage,
            {"$skip": skip_n},
            {"$limit": page_size},

            # Minimal lookup to get project.name AFTER pagination (cheap)
            {"$addFields": {"project_id": "$project.$id"}},
            {
                "$lookup": {
                    "from": "Project",
                    "localField": "project_id",
                    "foreignField": "_id",
                    "pipeline": [{"$project": {"name": 1}}],
                    "as": "project_doc",
                }
            },
            {"$set": {"project_name": {"$ifNull": [{"$first": "$project_doc.name"}, "-"]}}},
            {"$unset": ["project_id", "project_doc"]},

            # Only return what the FE needs
            {
                "$project": {
                    "_id": 1,
                    "created_at": 1,
                    "serial_number": 1,
                    "project_name": 1,
                    "cls_result": 1,
                }
            },
        ]

        # -------------------------- execute ----------------------------------
        docs: List[Dict[str, Any]] = await Scan.aggregate(pipeline).to_list()
        total: int = await Scan.find(match).count()

        # --------------------------- map rows --------------------------------
        rows: List[Dict[str, Any]] = []
        for d in docs or []:
            rows.append({
                "created_at": d.get("created_at"),
                "id": str(d.get("_id")),
                "part": d.get("project_name", "-"),  # human name
                "parts": [],                          # loaded lazily via fetch_row_parts
                "result": (d.get("cls_result") if d.get("cls_result") is not None else "Healthy"),
                "serial_number": d.get("serial_number"),
            })

        columns = [
            {"id": "serial_number", "header": "Serial Number"},
            {"id": "created_at", "header": "Created At"},
        ]

        return rows, total, columns
