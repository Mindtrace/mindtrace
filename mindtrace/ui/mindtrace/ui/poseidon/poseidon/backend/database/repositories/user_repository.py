from poseidon.backend.database.models.user import User
from poseidon.backend.core.config import settings
from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
from typing import Optional, List

backend = MongoMindtraceODMBackend(User, db_uri=settings.MONGO_URI, db_name=settings.DB_NAME)

class UserRepository:
    @staticmethod
    async def get_by_email(email: str) -> Optional[User]:
        await backend.initialize()
        users = await backend.find({"email": email})
        return users[0] if users else None

    @staticmethod
    async def get_by_username(username: str) -> Optional[User]:
        await backend.initialize()
        users = await backend.find({"username": username})
        return users[0] if users else None

    @staticmethod
    async def get_by_id(user_id: str) -> Optional[User]:
        """Get user by ID"""
        await backend.initialize()
        try:
            return await backend.get(user_id)
        except:
            return None

    @staticmethod
    async def create_user(user_data: dict) -> User:
        await backend.initialize()
        user = User(**user_data)
        return await backend.insert(user)
    
    @staticmethod
    async def get_by_organization(organization_id: str) -> List[User]:
        """Get all users in an organization (both active and inactive)"""
        await backend.initialize()
        return await backend.find({"organization_id": organization_id})
    
    @staticmethod
    async def get_all_users() -> List[User]:
        """Get all users across all organizations (super admin only)"""
        await backend.initialize()
        return await backend.find({})
    
    @staticmethod
    async def get_active_by_organization(organization_id: str) -> List[User]:
        """Get only active users in an organization"""
        await backend.initialize()
        return await backend.find({"organization_id": organization_id, "is_active": True})
    
    @staticmethod
    async def get_org_admins(organization_id: str) -> List[User]:
        """Get all organization admins"""
        await backend.initialize()
        return await backend.find({
            "organization_id": organization_id,
            "org_roles": {"$in": ["admin"]},
            "is_active": True
        })
    
    @staticmethod
    async def get_by_project(project_id: str) -> List[User]:
        """Get all users assigned to a project"""
        await backend.initialize()
        return await backend.find({
            "project_assignments.project_id": project_id,
            "is_active": True
        })
    
    @staticmethod
    async def assign_to_project(user_id: str, project_id: str, roles: List[str]) -> Optional[User]:
        """Assign user to project with roles"""
        await backend.initialize()
        user = await backend.get(user_id)
        if user:
            user.add_project_assignment(project_id, roles)
            user.update_timestamp()
            return await backend.update(user_id, user)
        return None
    
    @staticmethod
    async def remove_from_project(user_id: str, project_id: str) -> Optional[User]:
        """Remove user from project"""
        await backend.initialize()
        user = await backend.get(user_id)
        if user:
            user.remove_project_assignment(project_id)
            user.update_timestamp()
            return await backend.update(user_id, user)
        return None
    
    @staticmethod
    async def update_org_roles(user_id: str, roles: List[str]) -> Optional[User]:
        """Update user's organization roles"""
        await backend.initialize()
        user = await backend.get(user_id)
        if user:
            user.org_roles = roles
            user.update_timestamp()
            return await backend.update(user_id, user)
        return None
    
    @staticmethod
    async def deactivate_user(user_id: str) -> Optional[User]:
        """Deactivate user instead of deleting"""
        await backend.initialize()
        user = await backend.get(user_id)
        if user:
            user.is_active = False
            user.update_timestamp()
            return await backend.update(user_id, user)
        return None
    
    @staticmethod
    async def activate_user(user_id: str) -> Optional[User]:
        """Activate user account"""
        await backend.initialize()
        user = await backend.get(user_id)
        if user:
            user.is_active = True
            user.update_timestamp()
            return await backend.update(user_id, user)
        return None
    
    @staticmethod
    async def find_by_role(role: str) -> List[User]:
        """Find all users with a specific role"""
        await backend.initialize()
        return await backend.find({"org_roles": {"$in": [role]}}) 