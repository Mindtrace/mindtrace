from poseidon.backend.database.models.project import Project
from poseidon.backend.core.config import settings
from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
from typing import Optional, List

backend = MongoMindtraceODMBackend(Project, db_uri=settings.MONGO_URI, db_name=settings.DB_NAME)

class ProjectRepository:
    @staticmethod
    async def create_project(project_data: dict) -> Project:
        await backend.initialize()
        project = Project(**project_data)
        return await backend.insert(project)
    
    @staticmethod
    async def get_by_id(project_id: str) -> Optional[Project]:
        await backend.initialize()
        try:
            return await backend.get(project_id)
        except:
            return None
    
    @staticmethod
    async def get_by_organization(organization_id: str) -> List[Project]:
        """Get all projects for an organization"""
        await backend.initialize()
        return await backend.find({"organization_id": organization_id})
    
    @staticmethod
    async def get_active_by_organization(organization_id: str) -> List[Project]:
        """Get all active projects for an organization"""
        await backend.initialize()
        return await backend.find({"organization_id": organization_id, "status": "active"})
    
    @staticmethod
    async def get_by_owner(owner_id: str, organization_id: str) -> List[Project]:
        """Get projects owned by a specific user within an organization"""
        await backend.initialize()
        return await backend.find({"owner_id": owner_id, "organization_id": organization_id})
    
    @staticmethod
    async def get_by_status(organization_id: str, status: str) -> List[Project]:
        """Get projects by status within an organization"""
        await backend.initialize()
        return await backend.find({"organization_id": organization_id, "status": status})
    
    @staticmethod
    async def get_by_type(organization_id: str, project_type: str) -> List[Project]:
        """Get projects by type within an organization"""
        await backend.initialize()
        return await backend.find({"organization_id": organization_id, "project_type": project_type})
    
    @staticmethod
    async def search_by_name(organization_id: str, name_pattern: str) -> List[Project]:
        """Search projects by name pattern within an organization"""
        await backend.initialize()
        return await backend.find({
            "organization_id": organization_id,
            "name": {"$regex": name_pattern, "$options": "i"}
        })
    
    @staticmethod
    async def update_status(project_id: str, organization_id: str, status: str) -> Optional[Project]:
        """Update project status (with organization check for security)"""
        await backend.initialize()
        project = await backend.get(project_id)
        if project and project.organization_id == organization_id:
            project.set_status(status)
            return await backend.update(project_id, project.dict())
        return None
    
    @staticmethod
    async def update_settings(project_id: str, organization_id: str, settings: dict) -> Optional[Project]:
        """Update project settings (with organization check)"""
        await backend.initialize()
        project = await backend.get(project_id)
        if project and project.organization_id == organization_id:
            project.settings.update(settings)
            project.update_timestamp()
            return await backend.update(project_id, project.dict())
        return None
    
    @staticmethod
    async def add_tag(project_id: str, organization_id: str, tag: str) -> Optional[Project]:
        """Add tag to project (with organization check)"""
        await backend.initialize()
        project = await backend.get(project_id)
        if project and project.organization_id == organization_id:
            project.add_tag(tag)
            return await backend.update(project_id, project.dict())
        return None
    
    @staticmethod
    async def remove_tag(project_id: str, organization_id: str, tag: str) -> Optional[Project]:
        """Remove tag from project (with organization check)"""
        await backend.initialize()
        project = await backend.get(project_id)
        if project and project.organization_id == organization_id:
            project.remove_tag(tag)
            return await backend.update(project_id, project.dict())
        return None
    
    @staticmethod
    async def delete_project(project_id: str, organization_id: str) -> bool:
        """Delete project (with organization check for security)"""
        await backend.initialize()
        project = await backend.get(project_id)
        if project and project.organization_id == organization_id:
            await backend.delete(project_id)
            return True
        return False
    
    @staticmethod
    async def count_by_organization(organization_id: str) -> int:
        """Count projects in an organization"""
        await backend.initialize()
        projects = await backend.find({"organization_id": organization_id})
        return len(projects) 