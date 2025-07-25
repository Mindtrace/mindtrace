from poseidon.backend.database.models.scan_image import ScanImage
from poseidon.backend.database.models.enums import ScanImageStatus
from poseidon.backend.database.init import initialize_database
from typing import Optional, List

class ScanImageRepository:
    @staticmethod
    async def _ensure_init():
        """Ensure database is initialized before operations"""
        await initialize_database()

    @staticmethod
    async def create(scan_image_data: dict) -> ScanImage:
        """Create a new scan image"""
        await ScanImageRepository._ensure_init()
        scan_image = ScanImage(**scan_image_data)
        return await scan_image.insert()

    @staticmethod
    async def get_by_id(scan_image_id: str) -> Optional[ScanImage]:
        """Get scan image by ID"""
        await ScanImageRepository._ensure_init()
        try:
            return await ScanImage.get(scan_image_id, fetch_links=True)
        except:
            return None

    @staticmethod
    async def get_all() -> List[ScanImage]:
        """Get all scan images"""
        await ScanImageRepository._ensure_init()
        return await ScanImage.find_all().to_list()

    @staticmethod
    async def update(scan_image_id: str, update_data: dict) -> Optional[ScanImage]:
        """Update scan image"""
        await ScanImageRepository._ensure_init()
        try:
            scan_image = await ScanImage.get(scan_image_id)
            if scan_image:
                for key, value in update_data.items():
                    if hasattr(scan_image, key):
                        setattr(scan_image, key, value)
                scan_image.update_timestamp()
                await scan_image.save()
                return scan_image
        except:
            pass
        return None

    @staticmethod
    async def delete(scan_image_id: str) -> bool:
        """Delete scan image"""
        await ScanImageRepository._ensure_init()
        try:
            scan_image = await ScanImage.get(scan_image_id)
            if scan_image:
                await scan_image.delete()
                return True
        except:
            pass
        return False

    @staticmethod
    async def get_by_scan(scan_id: str) -> List[ScanImage]:
        """Get all images for a scan"""
        await ScanImageRepository._ensure_init()
        return await ScanImage.find(ScanImage.scan.id == scan_id).to_list()

    @staticmethod
    async def get_by_organization(org_id: str) -> List[ScanImage]:
        """Get all scan images for an organization"""
        await ScanImageRepository._ensure_init()
        return await ScanImage.find(ScanImage.organization.id == org_id).to_list()

    @staticmethod
    async def get_by_project(project_id: str) -> List[ScanImage]:
        """Get all scan images for a project"""
        await ScanImageRepository._ensure_init()
        return await ScanImage.find(ScanImage.project.id == project_id).to_list()

    @staticmethod
    async def get_by_camera(camera_id: str) -> List[ScanImage]:
        """Get all images from a specific camera"""
        await ScanImageRepository._ensure_init()
        return await ScanImage.find(ScanImage.camera.id == camera_id).to_list()

    @staticmethod
    async def get_by_status(status: ScanImageStatus) -> List[ScanImage]:
        """Get all scan images with specific status"""
        await ScanImageRepository._ensure_init()
        return await ScanImage.find(ScanImage.status == status).to_list()

    @staticmethod
    async def get_by_user(user_id: str) -> List[ScanImage]:
        """Get all scan images for a user"""
        await ScanImageRepository._ensure_init()
        return await ScanImage.find(ScanImage.user.id == user_id).to_list()

    @staticmethod
    async def update_status(scan_image_id: str, status: ScanImageStatus) -> Optional[ScanImage]:
        """Update scan image status"""
        await ScanImageRepository._ensure_init()
        return await ScanImageRepository.update(scan_image_id, {"status": status})

    @staticmethod
    async def get_by_filename(filename: str) -> Optional[ScanImage]:
        """Get scan image by filename"""
        await ScanImageRepository._ensure_init()
        return await ScanImage.find_one(ScanImage.file_name == filename)

    @staticmethod
    async def get_by_bucket_and_path(bucket_name: str, path: str) -> List[ScanImage]:
        """Get scan images by bucket name and path"""
        await ScanImageRepository._ensure_init()
        return await ScanImage.find(
            ScanImage.bucket_name == bucket_name,
            ScanImage.path == path
        ).to_list()

    @staticmethod
    async def get_processed_images() -> List[ScanImage]:
        """Get all processed scan images"""
        await ScanImageRepository._ensure_init()
        return await ScanImage.find(ScanImage.status == ScanImageStatus.PROCESSED).to_list()

    @staticmethod
    async def get_failed_images() -> List[ScanImage]:
        """Get all failed scan images"""
        await ScanImageRepository._ensure_init()
        return await ScanImage.find(ScanImage.status == ScanImageStatus.FAILED).to_list() 