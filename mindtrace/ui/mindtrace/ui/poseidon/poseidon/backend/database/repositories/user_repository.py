from poseidon.backend.database.models.user import User
from poseidon.backend.database.models.organization import Organization
from poseidon.backend.database.models.project import Project
from poseidon.backend.database.init import initialize_database
from typing import Optional, List

class UserRepository:
    @staticmethod
    async def _ensure_init():
        """Ensure database is initialized before operations"""
        await initialize_database()

    @staticmethod
    async def get_by_email(email: str) -> Optional[User]:
        """Get user by email"""
        await UserRepository._ensure_init()
        user = await User.find_one(User.email == email)
        if user:
            await user.fetch_all_links()
        return user

    @staticmethod
    async def get_by_id(user_id: str) -> Optional[User]:
        """Get user by ID"""
        await UserRepository._ensure_init()
        try:
            user = await User.get(user_id)
            if user:
                await user.fetch_all_links()
            return user
        except:
            return None

    @staticmethod
    async def create(user_data: dict) -> User:
        """Create a new user"""
        await UserRepository._ensure_init()
        
        # Convert organization_id to Link[Organization] if provided
        if "organization_id" in user_data:
            org_id = user_data.pop("organization_id")
            organization = await Organization.get(org_id)
            if organization:
                # For Beanie Links, we need to set the Link reference properly
                user_data["organization"] = organization
            else:
                raise ValueError(f"Organization with id {org_id} not found")
        
        # Convert org_roles to org_role (single) if provided
        if "org_roles" in user_data:
            org_roles = user_data.pop("org_roles")
            if org_roles:
                user_data["org_role"] = org_roles[0]  # Take first role
        
        # Remove project_assignments as it's now handled via projects Link
        if "project_assignments" in user_data:
            user_data.pop("project_assignments")
        
        user = User(**user_data)
        return await user.insert()
    
    @staticmethod
    async def update(user_id: str, update_data: dict) -> Optional[User]:
        """Update user with arbitrary data"""
        await UserRepository._ensure_init()
        try:
            user = await User.get(user_id)
            if user:
                for key, value in update_data.items():
                    if hasattr(user, key):
                        setattr(user, key, value)
                user.update_timestamp()
                await user.save()
                return user
        except:
            pass
        return None
    
    @staticmethod
    async def get_by_organization(organization_id: str) -> List[User]:
        """Get all users in an organization (both active and inactive)"""
        await UserRepository._ensure_init()
        try:
            # Use the organization Link to filter
            organization = await Organization.get(organization_id)
            if not organization:
                return []
            # Query by organization link
            users = await User.find(User.organization.id == organization.id).to_list()
            # Fetch all links for each user
            for user in users:
                await user.fetch_all_links()
            return users
        except:
            return []
    
    @staticmethod
    async def get_all_users() -> List[User]:
        """Get all users across all organizations (super admin only)"""
        await UserRepository._ensure_init()
        users = await User.find_all().to_list()
        # Fetch all links for each user
        for user in users:
            await user.fetch_all_links()
        return users
    
    @staticmethod
    async def get_all() -> List[User]:
        """Alias for get_all_users for consistency"""
        return await UserRepository.get_all_users()
    
    @staticmethod
    async def get_active_by_organization(organization_id: str) -> List[User]:
        """Get only active users in an organization"""
        await UserRepository._ensure_init()
        try:
            organization = await Organization.get(organization_id)
            if not organization:
                return []
            users = await User.find(
                User.organization.id == organization.id,
                User.is_active == True
            ).to_list()
            for user in users:
                await user.fetch_all_links()
            return users
        except:
            return []
    
    @staticmethod
    async def get_org_admins(organization_id: str) -> List[User]:
        """Get all organization admins"""
        await UserRepository._ensure_init()
        try:
            organization = await Organization.get(organization_id)
            if not organization:
                return []
            users = await User.find(
                User.organization.id == organization.id,
                User.org_role == "admin",
                User.is_active == True
            ).to_list()
            for user in users:
                await user.fetch_all_links()
            return users
        except:
            return []
    
    @staticmethod
    async def get_by_project(project_id: str) -> List[User]:
        """Get all users assigned to a project"""
        await UserRepository._ensure_init()
        try:
            project = await Project.get(project_id)
            if not project:
                return []
            # Find users who have this project in their projects list
            users = await User.find(User.projects.id == project.id).to_list()
            for user in users:
                await user.fetch_all_links()
            return users
        except:
            return []
    
    @staticmethod
    async def assign_to_project(user_id: str, project_id: str, roles: List[str] = None) -> Optional[User]:
        """Assign user to project"""
        await UserRepository._ensure_init()
        try:
            user = await User.get(user_id)
            project = await Project.get(project_id)
            
            if not user or not project:
                return None
            
            # Check if user is already assigned to this project
            project_already_assigned = any(str(p.id) == project_id for p in user.projects)
            
            if not project_already_assigned:
                user.projects.append(project)
                await user.save()
            else:
                # User already assigned to project
                pass
            
            return user
        except Exception as e:
            print(f"ERROR in assign_to_project: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    async def remove_from_project(user_id: str, project_id: str) -> Optional[User]:
        """Remove user from project"""
        await UserRepository._ensure_init()
        try:
            user = await User.get(user_id)
            project = await Project.get(project_id)
            
            if not user or not project:
                return None
            
            # Remove project from user's projects list
            user.projects = [p for p in user.projects if str(p.id) != project_id]
            await user.save()
            
            return user
        except Exception as e:
            print(f"ERROR in remove_from_project: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    async def update_org_role(user_id: str, role: str) -> Optional[User]:
        """Update user's organization role"""
        await UserRepository._ensure_init()
        try:
            user = await User.get(user_id)
            if user:
                user.org_role = role
                await user.save()
                return user
        except:
            pass
        return None
    
    @staticmethod
    async def deactivate(user_id: str) -> Optional[User]:
        """Deactivate user"""
        await UserRepository._ensure_init()
        try:
            user = await User.get(user_id)
            if user:
                user.is_active = False
                await user.save()
                return user
        except:
            pass
        return None
    
    @staticmethod
    async def activate(user_id: str) -> Optional[User]:
        """Activate user"""
        await UserRepository._ensure_init()
        try:
            user = await User.get(user_id)
            if user:
                user.is_active = True
                await user.save()
                return user
        except:
            pass
        return None
    
    @staticmethod
    async def delete(user_id: str) -> bool:
        """Delete user"""
        await UserRepository._ensure_init()
        try:
            user = await User.get(user_id)
            if user:
                await user.delete()
                return True
        except:
            pass
        return False 