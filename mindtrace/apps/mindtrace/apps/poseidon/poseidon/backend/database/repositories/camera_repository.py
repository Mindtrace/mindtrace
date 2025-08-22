from poseidon.backend.database.models.camera import Camera
from poseidon.backend.database.models.organization import Organization
from poseidon.backend.database.models.project import Project
from poseidon.backend.database.init import initialize_database
from typing import Optional, List

class CameraRepository:
    @staticmethod
    async def _ensure_init():
        """Ensure database is initialized before operations"""
        await initialize_database()

    @staticmethod
    async def get_all() -> List[Camera]:
        """Get all cameras from all organizations (for super admins)"""
        await CameraRepository._ensure_init()
        cameras = await Camera.find_all().to_list()
        # Fetch all links for each camera
        for camera in cameras:
            await camera.fetch_all_links()
        return cameras

    @staticmethod
    async def get_by_organization(organization_id: str) -> List[Camera]:
        """Get all cameras for an organization"""
        await CameraRepository._ensure_init()
        try:
            organization = await Organization.get(organization_id)
            if not organization:
                return []
            # Query by organization link
            cameras = await Camera.find(Camera.organization.id == organization.id).to_list()
            # Fetch all links for each camera
            for camera in cameras:
                await camera.fetch_all_links()
            return cameras
        except:
            return []

    @staticmethod
    async def get_by_ids(camera_ids: List[str]) -> List[Camera]:
        """Get multiple cameras by IDs"""
        await CameraRepository._ensure_init()
        cameras = []
        for camera_id in camera_ids:
            try:
                camera = await Camera.get(camera_id)
                if camera:
                    await camera.fetch_all_links()
                    cameras.append(camera)
            except:
                continue
        return cameras

    @staticmethod
    async def create_or_update(camera_data: dict) -> Camera:
        """Create or update a camera"""
        await CameraRepository._ensure_init()
        
        # Convert organization_id to Link[Organization] if provided
        if "organization_id" in camera_data:
            org_id = camera_data.pop("organization_id")
            organization = await Organization.get(org_id)
            camera_data["organization"] = organization
        
        # Convert project_id to Link[Project] if provided  
        if "project_id" in camera_data:
            project_id = camera_data.pop("project_id")
            project = await Project.get(project_id)
            camera_data["project"] = project
        
        # Convert created_by_id to Link[User] if provided
        if "created_by_id" in camera_data:
            from poseidon.backend.database.models.user import User
            user_id = camera_data.pop("created_by_id")
            user = await User.get(user_id)
            camera_data["created_by"] = user
        
        # Check if camera already exists by name and organization
        org_id = camera_data.get("organization")
        if org_id:
            existing_cameras = await Camera.find(
                Camera.name == camera_data.get("name"),
                Camera.organization.id == org_id.id
            ).to_list()
            
            if existing_cameras:
                # Update existing camera
                camera = existing_cameras[0]
                for key, value in camera_data.items():
                    setattr(camera, key, value)
                camera.update_timestamp()
                await camera.save()
                return camera
        
        # Create new camera
        camera = Camera(**camera_data)
        return await camera.insert()

    @staticmethod
    async def get_by_name(name: str, organization_id: str) -> Optional[Camera]:
        """Get camera by name within organization"""
        await CameraRepository._ensure_init()
        try:
            organization = await Organization.get(organization_id)
            if not organization:
                return None
            # Query by name and organization link
            cameras = await Camera.find(
                Camera.name == name,
                Camera.organization.id == organization.id
            ).to_list()
            if cameras:
                await cameras[0].fetch_all_links()
                return cameras[0]
            return None
        except:
            return None

    @staticmethod
    async def get_by_id(camera_id: str) -> Optional[Camera]:
        """Get camera by ID"""
        await CameraRepository._ensure_init()
        try:
            camera = await Camera.get(camera_id)
            if camera:
                await camera.fetch_all_links()
            return camera
        except:
            return None

    @staticmethod
    async def update(camera_id: str, update_data: dict) -> Optional[Camera]:
        """Update camera"""
        await CameraRepository._ensure_init()
        try:
            camera = await Camera.get(camera_id)
            if camera:
                for key, value in update_data.items():
                    if hasattr(camera, key):
                        setattr(camera, key, value)
                camera.update_timestamp()
                await camera.save()
                return camera
        except:
            pass
        return None

    @staticmethod
    async def delete(camera_id: str) -> bool:
        """Delete camera"""
        await CameraRepository._ensure_init()
        try:
            camera = await Camera.get(camera_id)
            if camera:
                await camera.delete()
                return True
        except:
            pass
        return False

    @staticmethod
    async def get_by_project_id(project_id: str) -> List[Camera]:
        """Get cameras by project ID"""
        await CameraRepository._ensure_init()
        try:
            project = await Project.get(project_id)
            if not project:
                return []
            cameras = await Camera.find(Camera.project.id == project.id).to_list()
            for camera in cameras:
                await camera.fetch_all_links()
            return cameras
        except:
            return []

    @staticmethod
    async def get_by_organization_and_project(organization_id: str, project_id: str) -> List[Camera]:
        """Get cameras by organization and project"""
        await CameraRepository._ensure_init()
        try:
            organization = await Organization.get(organization_id)
            project = await Project.get(project_id)
            if not organization or not project:
                return []
            cameras = await Camera.find(
                Camera.organization.id == organization.id,
                Camera.project.id == project.id
            ).to_list()
            for camera in cameras:
                await camera.fetch_all_links()
            return cameras
        except:
            return []

    @staticmethod
    async def assign_to_project(camera_name: str, project_id: str, organization_id: str) -> Optional[Camera]:
        """Assign camera to project"""
        await CameraRepository._ensure_init()
        try:
            camera = await CameraRepository.get_by_name(camera_name, organization_id)
            project = await Project.get(project_id)
            if camera and project:
                camera.project = project
                await camera.save()
                return camera
        except:
            pass
        return None

    @staticmethod
    async def update_configuration(camera_id: str, configuration: dict) -> Optional[Camera]:
        """Update camera configuration"""
        await CameraRepository._ensure_init()
        try:
            camera = await Camera.get(camera_id)
            if camera:
                camera.update_configuration(configuration)
                camera.update_timestamp()
                await camera.save()
                return camera
        except:
            pass
        return None
    
    @staticmethod
    async def get_by_project(project_id: str) -> List[Camera]:
        """Alias for get_by_project_id for consistency"""
        return await CameraRepository.get_by_project_id(project_id)