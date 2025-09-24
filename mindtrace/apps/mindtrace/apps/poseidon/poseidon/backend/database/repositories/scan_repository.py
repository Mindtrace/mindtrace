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
from poseidon.backend.database.init import initialize_database
from typing import Optional, List, Dict
from datetime import datetime
from beanie import PydanticObjectId

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
        try:
            # Follow existing pattern: get the linked object first
            from poseidon.backend.database.models.project import Project
                
            
            return await Scan.find(Scan.project.id == PydanticObjectId(project_id)).to_list()
        except Exception as e:
            print(f"Error in get_by_project: {e}")
            return []

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
    async def get_by_project_and_date_range(
        project_id: str, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Scan]:
        """Get scans for a project within a date range"""
        await ScanRepository._ensure_init()
        try:

            
            # Build query conditions
            conditions = [Scan.project.id == PydanticObjectId(project_id)]
            
            if start_date is not None:
                conditions.append(Scan.created_at >= start_date)
            if end_date:
                conditions.append(Scan.created_at <= end_date)
            
            
            return await Scan.find(*conditions).to_list()
        except Exception as e:
            print(f"Error in get_by_project_and_date_range: {e}")
            return []
    
    @staticmethod
    async def get_scan_count_by_date(
        project_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, int]:
        """Get scan counts grouped by date for a project"""
        await ScanRepository._ensure_init()
        scans = await ScanRepository.get_by_project_and_date_range(
            project_id, start_date, end_date
        )
        
        counts = {}
        for scan in scans:
            date_key = scan.created_at.strftime("%Y-%m-%d")
            counts[date_key] = counts.get(date_key, 0) + 1
        
        return counts 