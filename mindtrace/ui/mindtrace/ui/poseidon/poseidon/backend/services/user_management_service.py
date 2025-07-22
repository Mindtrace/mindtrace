"""User Management service for administrative operations.

This module provides user administration functionality including:
- User role management (organization and project level)
- Project assignment management
- User lifecycle operations (activate/deactivate)
- Organization user management
- Permission validation

This service is separate from AuthService to follow single responsibility principle.
AuthService handles authentication, UserManagementService handles administration.
"""

from typing import List, Optional
from poseidon.backend.database.repositories.user_repository import UserRepository
from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
from poseidon.backend.database.repositories.project_repository import ProjectRepository
from poseidon.backend.core.exceptions import UserNotFoundError
from poseidon.backend.database.models.enums import OrgRole


class UserManagementService:
    """Service class for handling user administration operations."""
    
    @staticmethod
    async def assign_user_to_project(
        user_id: str, 
        project_id: str, 
        roles: List[str],
        admin_organization_id: str
    ) -> dict:
        """Assign user to project with specific roles.
        
        Args:
            user_id: ID of user to assign
            project_id: ID of project to assign to
            roles: List of roles for the project
            admin_organization_id: Organization ID of admin making the request
            
        Returns:
            dict: Success response with updated user data
            
        Raises:
            UserNotFoundError: If user or project not found
            ValueError: If user/project not in same organization as admin
        """
        # Get user and validate
        user = await UserRepository.get_by_id(user_id)
        if not user:
            raise UserNotFoundError("User not found.")
        
        # Get project and validate
        project = await ProjectRepository.get_by_id(project_id)
        if not project:
            raise ValueError("Project not found.")
        
        # Fetch linked organization data
        await user.fetch_link(user.organization)
        await project.fetch_link(project.organization)
        
        # Validate organization access
        if str(user.organization.id) != admin_organization_id or str(project.organization.id) != admin_organization_id:
            raise ValueError("Access denied: User and project must be in your organization.")
        
        # Assign user to project
        updated_user = await UserRepository.assign_to_project(user_id, project_id, roles)
        return {"success": True, "user": updated_user}
    
    @staticmethod
    async def remove_user_from_project(
        user_id: str, 
        project_id: str,
        admin_organization_id: str
    ) -> dict:
        """Remove user from project.
        
        Args:
            user_id: ID of user to remove
            project_id: ID of project to remove from
            admin_organization_id: Organization ID of admin making the request
            
        Returns:
            dict: Success response
        """
        # Get user and validate
        user = await UserRepository.get_by_id(user_id)
        if not user:
            raise UserNotFoundError("User not found.")
        
        # Get project and validate
        project = await ProjectRepository.get_by_id(project_id)
        if not project:
            raise ValueError("Project not found.")
        
        # Fetch linked organization data
        await user.fetch_link(user.organization)
        await project.fetch_link(project.organization)
        
        # Validate organization access
        if str(user.organization.id) != admin_organization_id or str(project.organization.id) != admin_organization_id:
            raise ValueError("Access denied: User and project must be in your organization.")
        
        # Remove user from project
        await user.fetch_all_links()
        user.remove_project(project)
        await user.save()
        
        return {"success": True, "message": "User removed from project"}
    
    @staticmethod
    async def update_user_org_role(
        user_id: str, 
        role: str,
        admin_organization_id: str
    ) -> dict:
        """Update user's organization role.
        
        Args:
            user_id: ID of user to update
            role: New organization role
            admin_organization_id: Organization ID of admin making the request
            
        Returns:
            dict: Success response with updated user data
        """
        # Get user and validate
        user = await UserRepository.get_by_id(user_id)
        if not user:
            raise UserNotFoundError("User not found.")
        
        # Fetch linked organization data
        await user.fetch_link(user.organization)
        
        # Validate organization access
        if str(user.organization.id) != admin_organization_id:
            raise ValueError("Access denied: User must be in your organization.")
        
        # Update user's organization role
        updated_user = await UserRepository.update_org_role(user_id, role)
        return {"success": True, "user": updated_user}
    
    @staticmethod
    async def activate_user(user_id: str, admin_organization_id: str) -> dict:
        """Activate a user account.
        
        Args:
            user_id: ID of user to activate
            admin_organization_id: Organization ID of admin making the request
            
        Returns:
            dict: Success response
        """
        # Get user and validate
        user = await UserRepository.get_by_id(user_id)
        if not user:
            raise UserNotFoundError("User not found.")
        
        # Fetch linked organization data
        await user.fetch_link(user.organization)
        
        # Validate organization access
        if str(user.organization.id) != admin_organization_id:
            raise ValueError("Access denied: User must be in your organization.")
        
        # Activate user
        updated_user = await UserRepository.update(user_id, {"is_active": True})
        return {"success": True, "user": updated_user}
    
    @staticmethod
    async def deactivate_user(user_id: str, admin_organization_id: str) -> dict:
        """Deactivate a user account.
        
        Args:
            user_id: ID of user to deactivate
            admin_organization_id: Organization ID of admin making the request
            
        Returns:
            dict: Success response
        """
        # Get user and validate
        user = await UserRepository.get_by_id(user_id)
        if not user:
            raise UserNotFoundError("User not found.")
        
        # Fetch linked organization data
        await user.fetch_link(user.organization)
        
        # Validate organization access
        if str(user.organization.id) != admin_organization_id:
            raise ValueError("Access denied: User must be in your organization.")
        
        # Deactivate user
        updated_user = await UserRepository.update(user_id, {"is_active": False})
        return {"success": True, "user": updated_user}
    
    @staticmethod
    async def delete_user(user_id: str, admin_organization_id: str) -> dict:
        """Delete a user account.
        
        Args:
            user_id: ID of user to delete
            admin_organization_id: Organization ID of admin making the request
            
        Returns:
            dict: Success response
        """
        # Get user and validate
        user = await UserRepository.get_by_id(user_id)
        if not user:
            raise UserNotFoundError("User not found.")
        
        # Fetch linked organization data
        await user.fetch_link(user.organization)
        
        # Validate organization access
        if str(user.organization.id) != admin_organization_id:
            raise ValueError("Access denied: User must be in your organization.")
        
        # Delete user
        await UserRepository.delete(user_id)
        return {"success": True, "message": "User deleted successfully"}
    
    @staticmethod
    async def get_organization_users(organization_id: str) -> List:
        """Get all users in an organization.
        
        Args:
            organization_id: Organization ID
            
        Returns:
            List: List of users in the organization
        """
        return await UserRepository.get_by_organization(organization_id)
    
    @staticmethod
    async def get_all_users() -> List:
        """Get all users across all organizations (super admin only).
        
        Returns:
            List: List of all users
        """
        return await UserRepository.get_all_users()
    
    @staticmethod
    async def create_user_in_organization(
        first_name: str,
        last_name: str,
        email: str,
        password: str,
        admin_organization_id: str,
        org_role: str = None
    ) -> dict:
        """Create a new user in the organization.
        
        Args:
            first_name: First name for the new user
            last_name: Last name for the new user
            email: Email for the new user
            password: Password for the new user
            admin_organization_id: Organization ID where user will be created
            org_role: Organization role (defaults to "user")
            
        Returns:
            dict: Success response with created user data
        """
        # Default to user role if no role specified
        if not org_role:
            org_role = OrgRole.USER
        
        # Create the user
        from poseidon.backend.services.auth_service import AuthService
        result = await AuthService.register_user(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=password,
            organization_id=admin_organization_id,
            org_role=org_role
        )
        
        return {"success": True, "message": "User created successfully", "user": result}
    
    @staticmethod
    async def check_user_permission(
        user_id: str, 
        project_id: Optional[str] = None,
        required_org_role: Optional[str] = None,
        required_project_role: Optional[str] = None
    ) -> dict:
        """Check if user has required permissions.
        
        Args:
            user_id: User ID to check
            project_id: Optional project ID for project-level permissions
            required_org_role: Required organization role
            required_project_role: Required project role
            
        Returns:
            dict: Permission check results
        """
        user = await UserRepository.get_by_id(user_id)
        if not user:
            return {"has_permission": False, "reason": "User not found"}
        
        if not user.is_active:
            return {"has_permission": False, "reason": "User is inactive"}
        
        # Check organization role
        if required_org_role and not user.has_org_role(required_org_role):
            return {"has_permission": False, "reason": f"Missing organization role: {required_org_role}"}
        
        # Check project role (if user has projects assigned)
        if required_project_role and project_id:
            await user.fetch_all_links()
            project_found = any(str(p.id) == project_id for p in user.projects)
            if not project_found:
                return {"has_permission": False, "reason": f"User not assigned to project: {project_id}"}
        
        return {"has_permission": True, "user": user} 