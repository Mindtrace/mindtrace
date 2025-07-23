from poseidon.backend.database.models.scan import Scan
from poseidon.backend.database.models.enums import ScanStatus
from poseidon.backend.database.init import initialize_database
from typing import Optional, List

class ScanRepository:
    @staticmethod
    async def _ensure_init():
        """Ensure database is initialized before operations"""
        await initialize_database()

    @staticmethod
    async def create(scan_data: dict) -> Scan:
        """Create a new scan"""
        await ScanRepository._ensure_init()
        scan = Scan(**scan_data)
        return await scan.insert()

    @staticmethod
    async def get_by_id(scan_id: str) -> Optional[Scan]:
        """Get scan by ID"""
        await ScanRepository._ensure_init()
        try:
            return await Scan.get(scan_id, fetch_links=True)
        except:
            return None

    @staticmethod
    async def get_all() -> List[Scan]:
        """Get all scans"""
        await ScanRepository._ensure_init()
        return await Scan.find_all().to_list()

    @staticmethod
    async def update(scan_id: str, update_data: dict) -> Optional[Scan]:
        """Update scan"""
        await ScanRepository._ensure_init()
        try:
            scan = await Scan.get(scan_id)
            if scan:
                for key, value in update_data.items():
                    if hasattr(scan, key):
                        setattr(scan, key, value)
                scan.update_timestamp()
                await scan.save()
                return scan
        except:
            pass
        return None

    @staticmethod
    async def delete(scan_id: str) -> bool:
        """Delete scan"""
        await ScanRepository._ensure_init()
        try:
            scan = await Scan.get(scan_id)
            if scan:
                await scan.delete()
                return True
        except:
            pass
        return False

    @staticmethod
    async def get_by_organization(org_id: str) -> List[Scan]:
        """Get all scans for an organization"""
        await ScanRepository._ensure_init()
        return await Scan.find(Scan.organization.id == org_id).to_list()

    @staticmethod
    async def get_by_project(project_id: str) -> List[Scan]:
        """Get all scans for a project"""
        await ScanRepository._ensure_init()
        return await Scan.find(Scan.project.id == project_id).to_list()

    @staticmethod
    async def get_by_status(status: ScanStatus) -> List[Scan]:
        """Get all scans with specific status"""
        await ScanRepository._ensure_init()
        return await Scan.find(Scan.status == status).to_list()

    @staticmethod
    async def get_by_user(user_id: str) -> List[Scan]:
        """Get all scans for a user"""
        await ScanRepository._ensure_init()
        return await Scan.find(Scan.user.id == user_id).to_list()

    @staticmethod
    async def update_status(scan_id: str, status: ScanStatus) -> Optional[Scan]:
        """Update scan status"""
        await ScanRepository._ensure_init()
        return await ScanRepository.update(scan_id, {"status": status})

    @staticmethod
    async def update_results(scan_id: str, cls_result: str, cls_confidence: float, cls_pred_time: float) -> Optional[Scan]:
        """Update scan results"""
        await ScanRepository._ensure_init()
        return await ScanRepository.update(scan_id, {
            "cls_result": cls_result,
            "cls_confidence": cls_confidence,
            "cls_pred_time": cls_pred_time,
            "status": ScanStatus.COMPLETED
        })

    @staticmethod
    async def get_completed_scans() -> List[Scan]:
        """Get all completed scans"""
        await ScanRepository._ensure_init()
        return await Scan.find(Scan.status == ScanStatus.COMPLETED).to_list()

    @staticmethod
    async def get_failed_scans() -> List[Scan]:
        """Get all failed scans"""
        await ScanRepository._ensure_init()
        return await Scan.find(Scan.status == ScanStatus.FAILED).to_list() 