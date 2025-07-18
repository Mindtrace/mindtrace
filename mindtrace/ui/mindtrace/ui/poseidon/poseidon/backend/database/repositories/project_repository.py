from poseidon.backend.database.models.project import Project
from poseidon.backend.database.models.organization import Organization
from poseidon.backend.database.init import initialize_database
from typing import Optional, List

class ProjectRepository:
    @staticmethod
    async def _ensure_init():
        """Ensure database is initialized before operations"""
        await initialize_database()
    
    @staticmethod
    async def create(project_data: dict) -> Project:
        """Create a new project"""
        await ProjectRepository._ensure_init()
        
        # Convert organization_id to Link[Organization] if provided
        if "organization_id" in project_data:
            org_id = project_data.pop("organization_id")
            organization = await Organization.get(org_id)
            project_data["organization"] = organization
        
        # Convert owner_id to Link[User] if provided
        if "owner_id" in project_data:
            from poseidon.backend.database.models.user import User
            user_id = project_data.pop("owner_id")
            user = await User.get(user_id)
            project_data["owner"] = user
        
        project = Project(**project_data)
        return await project.insert()
    
    @staticmethod
    async def get_by_id(project_id: str) -> Optional[Project]:
        """Get project by ID"""
        await ProjectRepository._ensure_init()
        try:
            project = await Project.get(project_id)
            if project:
                # Fetch linked objects to ensure they are available
                await project.fetch_all_links()
            return project
        except:
            return None
    
    @staticmethod
    async def get_all() -> List[Project]:
        """Get all projects across all organizations (super admin only)"""
        await ProjectRepository._ensure_init()
        projects = await Project.find_all().to_list()
        # Fetch all links for each project
        for project in projects:
            await project.fetch_all_links()
        return projects
    
    @staticmethod
    async def update(project_id: str, update_data: dict) -> Optional[Project]:
        """Update project with arbitrary data"""
        await ProjectRepository._ensure_init()
        try:
            project = await Project.get(project_id)
            if project:
                for key, value in update_data.items():
                    if hasattr(project, key):
                        setattr(project, key, value)
                project.update_timestamp()
                await project.save()
                return project
        except:
            pass
        return None
    
    @staticmethod
    async def get_by_organization(organization_id: str) -> List[Project]:
        """Get all projects for an organization"""
        await ProjectRepository._ensure_init()
        try:
            organization = await Organization.get(organization_id)
            if not organization:
                return []
            # Query by organization link
            projects = await Project.find(Project.organization.id == organization.id).to_list()
            # Fetch all links for each project
            for project in projects:
                await project.fetch_all_links()
            return projects
        except:
            return []
    
    @staticmethod
    async def get_by_organization_and_status(organization_id: str, status: str) -> List[Project]:
        """Get projects by organization and status"""
        await ProjectRepository._ensure_init()
        try:
            organization = await Organization.get(organization_id)
            if not organization:
                return []
            # Query by organization link and status
            projects = await Project.find(
                Project.organization.id == organization.id,
                Project.status == status
            ).to_list()
            # Fetch all links for each project
            for project in projects:
                await project.fetch_all_links()
            return projects
        except:
            return []
    
    @staticmethod
    async def get_by_owner(owner_id: str, organization_id: str) -> List[Project]:
        """Get projects owned by a specific user within an organization"""
        await ProjectRepository._ensure_init()
        try:
            from poseidon.backend.database.models.user import User
            
            organization = await Organization.get(organization_id)
            user = await User.get(owner_id)
            
            if not organization or not user:
                return []
            
            # Query by organization and owner links
            projects = await Project.find(
                Project.organization.id == organization.id,
                Project.owner.id == user.id
            ).to_list()
            
            # Fetch all links for each project
            for project in projects:
                await project.fetch_all_links()
            return projects
        except:
            return []
    
    @staticmethod
    async def search_by_name(organization_id: str, name_pattern: str) -> List[Project]:
        """Search projects by name pattern within an organization"""
        await ProjectRepository._ensure_init()
        try:
            organization = await Organization.get(organization_id)
            if not organization:
                return []
            
            # Query by organization link and name pattern
            projects = await Project.find(
                Project.organization.id == organization.id,
                {"name": {"$regex": name_pattern, "$options": "i"}}
            ).to_list()
            
            # Fetch all links for each project
            for project in projects:
                await project.fetch_all_links()
            return projects
        except:
            return []
    
    @staticmethod
    async def update_with_org_check(project_id: str, organization_id: str, update_data: dict) -> Optional[Project]:
        """Update project with organization security check"""
        await ProjectRepository._ensure_init()
        try:
            project = await Project.get(project_id)
            if project:
                await project.fetch_all_links()
                # Check if project belongs to the organization
                if project.organization and str(project.organization.id) == organization_id:
                    for key, value in update_data.items():
                        if hasattr(project, key):
                            setattr(project, key, value)
                    project.update_timestamp()
                    await project.save()
                    return project
        except:
            pass
        return None
    
    @staticmethod
    async def delete(project_id: str, organization_id: str = None) -> bool:
        """Delete project (with optional organization check for security)"""
        await ProjectRepository._ensure_init()
        try:
            if organization_id:
                project = await Project.get(project_id)
                if project:
                    await project.fetch_all_links()
                    # Check if project belongs to the organization
                    if not project.organization or str(project.organization.id) != organization_id:
                        return False
            project = await Project.get(project_id)
            if project:
                await project.delete()
                return True
            return False
        except:
            return False
    
    @staticmethod
    async def count_by_organization(organization_id: str) -> int:
        """Count projects in an organization"""
        await ProjectRepository._ensure_init()
        try:
            organization = await Organization.get(organization_id)
            if not organization:
                return 0
            # Count projects by organization link
            count = await Project.find(Project.organization.id == organization.id).count()
            return count
        except:
            return 0
    
    @staticmethod
    def get_organization_id(project: Project) -> Optional[str]:
        """Helper method to get organization ID from project"""
        if project.organization:
            return str(project.organization.id)
        return None
    
    @staticmethod
    def get_owner_id(project: Project) -> Optional[str]:
        """Helper method to get owner ID from project"""
        if project.owner:
            return str(project.owner.id)
        return None 