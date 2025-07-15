from poseidon.backend.database.models.camera import Camera
from poseidon.backend.core.config import settings
from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
from typing import Optional, List

backend = MongoMindtraceODMBackend(Camera, db_uri=settings.MONGO_URI, db_name=settings.DB_NAME)

class CameraRepository:
    @staticmethod
    async def get_by_organization(organization_id: str) -> List[Camera]:
        """Get all cameras for an organization"""
        await backend.initialize()
        return await backend.find({"organization_id": organization_id})

    @staticmethod
    async def get_by_ids(camera_ids: List[str]) -> List[Camera]:
        """Get multiple cameras by IDs"""
        await backend.initialize()
        cameras = []
        for camera_id in camera_ids:
            try:
                camera = await backend.get(camera_id)
                if camera:
                    cameras.append(camera)
            except:
                continue
        return cameras

    @staticmethod
    async def create_or_update(camera_data: dict) -> Camera:
        """Create or update a camera"""
        await backend.initialize()
        
        # Check if camera already exists by name and organization
        existing_cameras = await backend.find({
            "name": camera_data.get("name"),
            "organization_id": camera_data.get("organization_id")
        })
        
        if existing_cameras:
            # Update existing camera
            camera = existing_cameras[0]
            for key, value in camera_data.items():
                setattr(camera, key, value)
            camera.update_timestamp()
            return await backend.update(camera)
        else:
            # Create new camera
            camera = Camera(**camera_data)
            return await backend.insert(camera)

    @staticmethod
    async def get_by_name(name: str, organization_id: str) -> Optional[Camera]:
        """Get camera by name within organization"""
        await backend.initialize()
        cameras = await backend.find({"name": name, "organization_id": organization_id})
        return cameras[0] if cameras else None

    @staticmethod
    async def update_status(camera_id: str, status: str) -> Optional[Camera]:
        """Update camera status"""
        await backend.initialize()
        try:
            camera = await backend.get(camera_id)
            if camera:
                camera.update_status(status)
                return await backend.update(camera)
        except:
            pass
        return None

    @staticmethod
    async def get_by_id(camera_id: str) -> Optional[Camera]:
        """Get camera by ID"""
        await backend.initialize()
        try:
            return await backend.get(camera_id)
        except:
            return None

    @staticmethod
    async def delete(camera_id: str) -> bool:
        """Delete a camera"""
        await backend.initialize()
        try:
            await backend.delete(camera_id)
            return True
        except:
            return False

    @staticmethod
    async def get_active_by_organization(organization_id: str) -> List[Camera]:
        """Get only active cameras in an organization"""
        await backend.initialize()
        return await backend.find({
            "organization_id": organization_id,
            "status": "active"
        })

    @staticmethod
    async def update_configuration(camera_id: str, configuration: dict) -> Optional[Camera]:
        """Update camera configuration"""
        await backend.initialize()
        try:
            camera = await backend.get(camera_id)
            if camera:
                camera.update_configuration(configuration)
                return await backend.update(camera)
        except:
            pass
        return None