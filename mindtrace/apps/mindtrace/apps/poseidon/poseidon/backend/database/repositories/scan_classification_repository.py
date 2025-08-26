from poseidon.backend.database.models.scan_classification import ScanClassification
from poseidon.backend.database.init import initialize_database
from typing import Optional, List, Dict
from datetime import datetime

class ScanClassificationRepository:
    @staticmethod
    async def _ensure_init():
        """Ensure database is initialized before operations"""
        await initialize_database()

    @staticmethod
    async def create(classification_data: dict) -> ScanClassification:
        """Create a new scan classification"""
        await ScanClassificationRepository._ensure_init()
        classification = ScanClassification(**classification_data)
        return await classification.insert()

    @staticmethod
    async def get_by_id(classification_id: str) -> Optional[ScanClassification]:
        """Get scan classification by ID"""
        await ScanClassificationRepository._ensure_init()
        try:
            return await ScanClassification.get(classification_id, fetch_links=True)
        except:
            return None

    @staticmethod
    async def get_all() -> List[ScanClassification]:
        """Get all scan classifications"""
        await ScanClassificationRepository._ensure_init()
        return await ScanClassification.find_all().to_list()

    @staticmethod
    async def update(classification_id: str, update_data: dict) -> Optional[ScanClassification]:
        """Update scan classification"""
        await ScanClassificationRepository._ensure_init()
        try:
            classification = await ScanClassification.get(classification_id)
            if classification:
                for key, value in update_data.items():
                    if hasattr(classification, key):
                        setattr(classification, key, value)
                classification.update_timestamp()
                await classification.save()
                return classification
        except:
            pass
        return None

    @staticmethod
    async def delete(classification_id: str) -> bool:
        """Delete scan classification"""
        await ScanClassificationRepository._ensure_init()
        try:
            classification = await ScanClassification.get(classification_id)
            if classification:
                await classification.delete()
                return True
        except:
            pass
        return False

    @staticmethod
    async def get_by_image(image_id: str) -> List[ScanClassification]:
        """Get all classifications for an image"""
        await ScanClassificationRepository._ensure_init()
        return await ScanClassification.find(ScanClassification.image.id == image_id).to_list()

    @staticmethod
    async def get_by_scan(scan_id: str) -> List[ScanClassification]:
        """Get all classifications for a scan"""
        await ScanClassificationRepository._ensure_init()
        return await ScanClassification.find(ScanClassification.scan.id == scan_id).to_list()

    @staticmethod
    async def get_by_name(name: str) -> List[ScanClassification]:
        """Get all classifications with a specific name/label"""
        await ScanClassificationRepository._ensure_init()
        return await ScanClassification.find(ScanClassification.name == name).to_list()

    @staticmethod
    async def get_by_detected_class(det_cls: str) -> List[ScanClassification]:
        """Get all classifications with a specific detected class"""
        await ScanClassificationRepository._ensure_init()
        return await ScanClassification.find(ScanClassification.det_cls == det_cls).to_list()

    @staticmethod
    async def get_high_confidence_classifications(threshold: float = 0.8) -> List[ScanClassification]:
        """Get classifications with confidence above threshold"""
        await ScanClassificationRepository._ensure_init()
        return await ScanClassification.find(ScanClassification.cls_confidence >= threshold).to_list()

    @staticmethod
    async def get_with_bounding_boxes() -> List[ScanClassification]:
        """Get classifications that have bounding box data"""
        await ScanClassificationRepository._ensure_init()
        return await ScanClassification.find(
            ScanClassification.det_x != None,
            ScanClassification.det_y != None,
            ScanClassification.det_w != None,
            ScanClassification.det_h != None
        ).to_list()

    @staticmethod
    async def get_by_confidence_range(min_confidence: float, max_confidence: float) -> List[ScanClassification]:
        """Get classifications within a confidence range"""
        await ScanClassificationRepository._ensure_init()
        return await ScanClassification.find(
            ScanClassification.cls_confidence >= min_confidence,
            ScanClassification.cls_confidence <= max_confidence
        ).to_list()

    @staticmethod
    async def create_batch(classifications_data: List[dict]) -> List[ScanClassification]:
        """Create multiple classifications in batch"""
        await ScanClassificationRepository._ensure_init()
        classifications = [ScanClassification(**data) for data in classifications_data]
        return await ScanClassification.insert_many(classifications)

    @staticmethod
    async def delete_by_image(image_id: str) -> int:
        """Delete all classifications for an image"""
        await ScanClassificationRepository._ensure_init()
        classifications = await ScanClassification.find(ScanClassification.image.id == image_id).to_list()
        count = len(classifications)
        for classification in classifications:
            await classification.delete()
        return count

    @staticmethod
    async def delete_by_scan(scan_id: str) -> int:
        """Delete all classifications for a scan"""
        await ScanClassificationRepository._ensure_init()
        classifications = await ScanClassification.find(ScanClassification.scan.id == scan_id).to_list()
        count = len(classifications)
        for classification in classifications:
            await classification.delete()
        return count
    
    @staticmethod
    async def get_by_project_and_date_range(
        project_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[ScanClassification]:
        """Get classifications for a project within a date range"""
        await ScanClassificationRepository._ensure_init()
        try:
            # Note: This assumes ScanClassification has a relation to project through scan
            # We'll need to join through the scan model
            from poseidon.backend.database.models.scan import Scan
            
            # First get all scans for the project within date range
            scan_conditions = [Scan.project.id == project_id]
            if start_date:
                scan_conditions.append(Scan.created_at >= start_date)
            if end_date:
                scan_conditions.append(Scan.created_at <= end_date)
            
            scans = await Scan.find(*scan_conditions).to_list()
            if not scans:
                return []
            
            scan_ids = [scan.id for scan in scans]
            
            # Then get classifications for those scans
            return await ScanClassification.find(ScanClassification.scan.id.in_(scan_ids)).to_list()
        except Exception as e:
            print(f"Error in get_by_project_and_date_range: {e}")
            return []
    
    @staticmethod
    async def get_by_camera_and_date_range(
        camera_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[ScanClassification]:
        """Get classifications for a camera within a date range"""
        await ScanClassificationRepository._ensure_init()
        try:
            # Get classifications through ScanImage -> Camera relationship
            from poseidon.backend.database.models.scan_image import ScanImage
            
            # Get ScanImages for the camera within date range
            image_conditions = [ScanImage.camera.id == camera_id]
            if start_date:
                image_conditions.append(ScanImage.created_at >= start_date)
            if end_date:
                image_conditions.append(ScanImage.created_at <= end_date)
            
            images = await ScanImage.find(*image_conditions).to_list()
            if not images:
                return []
            
            image_ids = [image.id for image in images]
            
            # Get classifications for those images
            return await ScanClassification.find(ScanClassification.image.id.in_(image_ids)).to_list()
        except Exception as e:
            print(f"Error in get_by_camera_and_date_range: {e}")
            return []
    
    @staticmethod
    async def get_defect_frequency_by_project(
        project_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, int]:
        """Get defect frequency counts by type for a project"""
        await ScanClassificationRepository._ensure_init()
        classifications = await ScanClassificationRepository.get_by_project_and_date_range(
            project_id, start_date, end_date
        )
        
        frequency = {}
        for cls in classifications:
            defect_type = cls.name or "Unknown"
            frequency[defect_type] = frequency.get(defect_type, 0) + 1
        
        return frequency 