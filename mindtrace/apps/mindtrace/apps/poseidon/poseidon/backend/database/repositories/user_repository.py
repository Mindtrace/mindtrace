from typing import Optional, List
from poseidon.backend.database.models.user import User
from poseidon.backend.database.models.organization import Organization
from poseidon.backend.database.models.project import Project
from poseidon.backend.database.init import initialize_database
from poseidon.backend.database.models.enums import OrgRole

class UserRepository:
    @staticmethod
    async def _ensure_init():
        """Ensure database is initialized before operations"""
        await initialize_database()

    # ------------------------------- reads ------------------------------------ 
    @staticmethod
    async def get_by_email(email: str) -> Optional[User]:
        """Get user by email (case-insensitive)"""
        await UserRepository._ensure_init()
        if not email:
            return None
        e = email.strip().lower()
        user = await User.find_one(User.email == e)
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
    async def find_by_role(role: str | OrgRole) -> List[User]:
        """Find users by org role (string or enum)"""
        await UserRepository._ensure_init()
        r = getattr(role, "value", role)
        users = await User.find(User.org_role == r).to_list()
        for u in users:
            await u.fetch_all_links()
        return users

    @staticmethod
    async def get_by_organization(organization_id: str) -> List[User]:
        """Get all users in an organization (both active and inactive)"""
        await UserRepository._ensure_init()
        try:
            organization = await Organization.get(organization_id)
            if not organization:
                return []
            users = await User.find(User.organization.id == organization.id).to_list()
            for user in users:
                await user.fetch_all_links()
            return users
        except:
            return []

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
                User.is_active == True,
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
            admin_val = getattr(OrgRole.ADMIN, "value", "admin")
            users = await User.find(
                User.organization.id == organization.id,
                User.org_role == admin_val,
                User.is_active == True,
            ).to_list()
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
        for user in users:
            await user.fetch_all_links()
        return users

    @staticmethod
    async def get_all() -> List[User]:
        """Alias for get_all_users for consistency"""
        return await UserRepository.get_all_users()

    @staticmethod
    async def get_by_project(project_id: str) -> List[User]:
        """Get all users assigned to a project"""
        await UserRepository._ensure_init()
        try:
            project = await Project.get(project_id)
            if not project:
                return []
            users = await User.find(User.projects.id == project.id).to_list()
            for user in users:
                await user.fetch_all_links()
            return users
        except:
            return []

    # ------------------------------ writes ------------------------------------

    @staticmethod
    async def create(user_data: dict) -> User:
        """Create a new user"""
        await UserRepository._ensure_init()

        # Normalize email to lowercase
        if "email" in user_data and user_data["email"]:
            user_data["email"] = user_data["email"].strip().lower()

        # Convert organization_id to Link[Organization] if provided
        if "organization_id" in user_data:
            org_id = user_data.pop("organization_id")
            organization = await Organization.get(org_id)
            if organization:
                user_data["organization"] = organization
            else:
                raise ValueError(f"Organization with id {org_id} not found")

        # Back-compat: collapse list roles to single role if ever passed
        if "org_roles" in user_data:
            org_roles = user_data.pop("org_roles")
            if org_roles:
                user_data["org_role"] = getattr(org_roles[0], "value", org_roles[0])

        # Ensure org_role is stored as a string value if enum was passed
        if "org_role" in user_data:
            user_data["org_role"] = getattr(user_data["org_role"], "value", user_data["org_role"])

        # Remove legacy fields we no longer store
        user_data.pop("project_assignments", None)   # projects are Links
        user_data.pop("username", None)              # username removed

        user = User(**user_data)
        return await user.insert()

    @staticmethod
    async def update(user_id: str, update_data: dict) -> Optional[User]:
        """Update user with arbitrary data"""
        await UserRepository._ensure_init()
        try:
            user = await User.get(user_id)
            if not user:
                return None

            # Normalize email if updated
            if "email" in update_data and update_data["email"]:
                update_data["email"] = update_data["email"].strip().lower()

            # Allow updating role safely (enum or string)
            if "org_role" in update_data:
                update_data["org_role"] = getattr(update_data["org_role"], "value", update_data["org_role"])

            # Handle organization change (optional)
            if "organization_id" in update_data:
                org_id = update_data.pop("organization_id")
                organization = await Organization.get(org_id)
                if not organization:
                    raise ValueError(f"Organization with id {org_id} not found")
                setattr(user, "organization", organization)

            # Assign other simple fields
            for key, value in update_data.items():
                if hasattr(user, key):
                    setattr(user, key, value)

            user.update_timestamp()
            await user.save()
            await user.fetch_all_links()
            return user
        except:
            return None

    @staticmethod
    async def assign_to_project(user_id: str, project_id: str, roles: List[str] = None) -> Optional[User]:
        """Assign user to project (roles list currently unused; projects are Links)"""
        await UserRepository._ensure_init()
        try:
            user = await User.get(user_id)
            project = await Project.get(project_id)
            if not user or not project:
                return None

            # Ensure projects list exists
            if getattr(user, "projects", None) is None:
                user.projects = []

            # Avoid duplicates
            if not any(str(p.id) == project_id for p in user.projects):
                user.projects.append(project)
                await user.save()

            await user.fetch_all_links()
            return user
        except:
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

            user.projects = [p for p in (user.projects or []) if str(p.id) != project_id]
            await user.save()
            await user.fetch_all_links()
            return user
        except:
            return None

    @staticmethod
    async def update_org_role(user_id: str, role: str | OrgRole) -> Optional[User]:
        """Update user's organization role"""
        await UserRepository._ensure_init()
        try:
            user = await User.get(user_id)
            if not user:
                return None
            user.org_role = getattr(role, "value", role)
            await user.save()
            await user.fetch_all_links()
            return user
        except:
            return None

    @staticmethod
    async def deactivate(user_id: str) -> Optional[User]:
        """Deactivate user"""
        await UserRepository._ensure_init()
        try:
            user = await User.get(user_id)
            if not user:
                return None
            user.is_active = False
            await user.save()
            await user.fetch_all_links()
            return user
        except:
            return None

    @staticmethod
    async def activate(user_id: str) -> Optional[User]:
        """Activate user"""
        await UserRepository._ensure_init()
        try:
            user = await User.get(user_id)
            if not user:
                return None
            user.is_active = True
            await user.save()
            await user.fetch_all_links()
            return user
        except:
            return None

    @staticmethod
    async def delete(user_id: str) -> bool:
        """Delete user"""
        await UserRepository._ensure_init()
        try:
            user = await User.get(user_id)
            if not user:
                return False
            await user.delete()
            return True
        except:
            return False
