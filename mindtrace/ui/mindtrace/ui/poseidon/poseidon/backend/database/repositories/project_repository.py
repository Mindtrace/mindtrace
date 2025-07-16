from poseidon.backend.database.models.project import Project
from poseidon.backend.core.config import settings
from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
from typing import Optional, List

backend = MongoMindtraceODMBackend(Project, db_uri=settings.MONGO_URI, db_name=settings.DB_NAME)

class ProjectRepository:
    @staticmethod
    async def create(project_data: dict) -> Project:
        """Create a new project"""
        await backend.initialize()
        project = Project(**project_data)
        return await backend.insert(project)
    
    @staticmethod
    async def get_by_id(project_id: str) -> Optional[Project]:
        """Get project by ID"""
        await backend.initialize()
        try:
            return await backend.get(project_id)
        except:
            return None
    
    @staticmethod
    async def get_all() -> List[Project]:
        """Get all projects across all organizations (super admin only)"""
        await backend.initialize()
        return await backend.find({})
    
    @staticmethod
    async def update(project_id: str, update_data: dict) -> Optional[Project]:
        """Update project with arbitrary data"""
        await backend.initialize()
        try:
            project = await backend.get(project_id)
            if project:
                for key, value in update_data.items():
                    if hasattr(project, key):
                        setattr(project, key, value)
                project.update_timestamp()
                return await backend.update(project_id, project)
        except:
            pass
            return None
    
    @staticmethod
    async def get_by_organization(organization_id: str) -> List[Project]:
        """Get all projects for an organization"""
        await backend.initialize()
        return await backend.find({"organization_id": organization_id})
    
    @staticmethod
    async def get_by_organization_and_status(organization_id: str, status: str) -> List[Project]:
        """Get projects by organization and status"""
        await backend.initialize()
        return await backend.find({"organization_id": organization_id, "status": status})
    
    @staticmethod
    async def get_by_owner(owner_id: str, organization_id: str) -> List[Project]:
        """Get projects owned by a specific user within an organization"""
        await backend.initialize()
        return await backend.find({"owner_id": owner_id, "organization_id": organization_id})
    
    @staticmethod
    async def search_by_name(organization_id: str, name_pattern: str) -> List[Project]:
        """Search projects by name pattern within an organization"""
        await backend.initialize()
        return await backend.find({
            "organization_id": organization_id,
            "name": {"$regex": name_pattern, "$options": "i"}
        })
    
    @staticmethod
    async def update_with_org_check(project_id: str, organization_id: str, update_data: dict) -> Optional[Project]:
        """Update project with organization security check"""
        await backend.initialize()
        try:
            project = await backend.get(project_id)
            if project and project.organization_id == organization_id:
                for key, value in update_data.items():
                    if hasattr(project, key):
                        setattr(project, key, value)
            project.update_timestamp()
            return await backend.update(project_id, project)
        except:
            pass
        return None
    
    @staticmethod
    async def delete(project_id: str, organization_id: str = None) -> bool:
        """Delete project (with optional organization check for security)"""
        await backend.initialize()
        try:
            if organization_id:
                project = await backend.get(project_id)
                if not project or project.organization_id != organization_id:
                    return False
            await backend.delete(project_id)
            return True
        except:
            return False
    
    @staticmethod
    async def count_by_organization(organization_id: str) -> int:
        """Count projects in an organization"""
        await backend.initialize()
        projects = await backend.find({"organization_id": organization_id})
        return len(projects) 