# metrics_repository.py
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from beanie import PydanticObjectId
from poseidon.backend.database.init import initialize_database
from poseidon.backend.database.models.scan import Scan
from poseidon.backend.database.models.scan_classification import ScanClassification


def _day_bounds(start: datetime, end: datetime):
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    s = start.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    e = end.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return s, e


class MetricsRepository:
    @staticmethod
    async def _ensure_init():
        await initialize_database()

    @staticmethod
    async def scans_timeseries(project_id: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        await MetricsRepository._ensure_init()
        pid = PydanticObjectId(project_id)
        s, e = _day_bounds(start, end)

        pipeline = [
            {"$match": {"project.$id": pid, "created_at": {"$gte": s, "$lt": e}}},
            {
                "$project": {
                    "day": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                    "status_lc": {"$toLower": {"$ifNull": ["$status", ""]}},
                    "cls_lc": {"$toLower": {"$ifNull": ["$cls_result", ""]}},
                }
            },
            {
                "$group": {
                    "_id": "$day",
                    "count": {"$sum": 1},
                    "defects": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$or": [
                                        {"$eq": ["$status_lc", "failed"]},
                                        {"$eq": ["$cls_lc", "defective"]},
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "date": "$_id",
                    "count": 1,
                    "defects": 1,
                    "defect_rate": {
                        "$cond": [{"$gt": ["$count", 0]}, {"$multiply": [{"$divide": ["$defects", "$count"]}, 100]}, 0]
                    },
                }
            },
            {"$sort": {"date": 1}},
        ]
        res = await Scan.aggregate(pipeline).to_list()
        return res

    @staticmethod
    async def classification_facets(project_id: str, start: datetime, end: datetime, top_n: int = 10) -> Dict[str, Any]:
        await MetricsRepository._ensure_init()
        pid = PydanticObjectId(project_id)
        s, e = _day_bounds(start, end)

        pipeline = [
            {"$match": {"scan_project_id": pid, "created_at": {"$gte": s, "$lt": e}}},
            {
                "$project": {  # early project
                    "_id": 0,
                    "det_cls": 1,
                    "name": 1,
                    "is_defect": 1,
                }
            },
            {"$addFields": {"is_defect_int": {"$cond": ["$is_defect", 1, 0]}}},
            {
                "$facet": {
                    "defect_histogram": [
                        {"$match": {"det_cls": {"$ne": None, "$ne": "Healthy"}}},
                        {"$sortByCount": "$det_cls"},
                        {"$limit": top_n},
                        {"$project": {"_id": 0, "defect_type": "$_id", "count": "$count"}},
                    ],
                    "weld_defect_rate": [
                        {
                            "$group": {
                                "_id": "$name",
                                "total_inspections": {"$sum": 1},
                                "defective_inspections": {"$sum": "$is_defect_int"},
                            }
                        },
                        {
                            "$project": {
                                "_id": 0,
                                "weld_id": "$_id",
                                "total_inspections": 1,
                                "defective_inspections": 1,
                                "defect_rate": {
                                    "$cond": [
                                        {"$gt": ["$total_inspections", 0]},
                                        {
                                            "$round": [
                                                {
                                                    "$multiply": [
                                                        {"$divide": ["$defective_inspections", "$total_inspections"]},
                                                        100,
                                                    ]
                                                },
                                                2,
                                            ]
                                        },
                                        0,
                                    ]
                                },
                            }
                        },
                        {"$sort": {"defect_rate": -1, "weld_id": 1}},
                    ],
                }
            },
        ]
        res = await ScanClassification.aggregate(pipeline).to_list()
        return res[0] if res else {"defect_histogram": [], "weld_defect_rate": []}
