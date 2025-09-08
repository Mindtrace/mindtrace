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


class TableRepository:
    # ----------------- init -----------------
    @staticmethod
    async def _ensure_init():
        await initialize_database()

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
            {"$match": {"serial_number": {"$regex": q, "$options": "i"}}} if q else {"$match": {}},
            {"$set": {"result": {"$ifNull": ["$cls_result", "Healthy"]}}},
            {"$match": {"result": result}} if result and result != "All" else {"$match": {}},
            {"$addFields": {"project_id": "$project.$id"}},
            {"$lookup": {
                "from": "Project",
                "localField": "project_id",
                "foreignField": "_id",
                "as": "project_doc",
            }},
            {"$set": {"project_name": {"$ifNull": [{"$first": "$project_doc.name"}, "-"]}}},
            {"$unset": ["project_id", "project_doc"]},
            {"$addFields": {
                "image_ids": {
                    "$map": {
                        "input": {"$ifNull": ["$images", []]},
                        "as": "ref",
                        "in": "$$ref.$id"
                    }
                }
            }},
            {"$lookup": {
                "from": "ScanImage",
                "localField": "image_ids",
                "foreignField": "_id",
                "as": "images",
            }},
            {"$lookup": {
                "from": "ScanClassification",
                "let": {"imgIds": "$image_ids"},
                "pipeline": [
                    {"$match": {"$expr": {"$in": ["$image.$id", "$$imgIds"]}}},
                ],
                "as": "classifications",
            }},
            {"$sort": {"created_at": -1 if sort_dir == "desc" else 1, "_id": -1}},
            {"$skip": max(0, (page - 1) * page_size)},
            {"$limit": page_size},
        ]

        docs: List[Dict[str, Any]] = await Scan.aggregate(pipeline).to_list()

        rows: List[Dict[str, Any]] = []

        print(f"Docs fetched: {len(docs)}")
        for d in docs:
            parts = []
            for classification in d.get("classifications", []) or []:
                image_ref = classification.get("image", {})
                part_status = classification.get("det_cls") or "Healthy"
                name = classification.get("name") or "Camera"
                
                if part_status.lower() != "healthy":
                    print(f"  - Found defect: {part_status} on {name}")
                parts.append({
                    "name": name,
                    "status": part_status,
                })
            
            for img in (d.get("images", []) or []):
                full_path = img.get("full_path")
                if full_path:
                    img_url = presign_url(full_path)
                else:
                    img_url = ""
            
                parts.append({
                    "image_url": img_url,
                })
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
