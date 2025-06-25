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
        
        # Validate organization access
        if user.organization_id != admin_organization_id or project.organization_id != admin_organization_id:
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
            dict: Success response with updated user data
        """
        # Get user and validate organization
        user = await UserRepository.get_by_id(user_id)
        if not user or user.organization_id != admin_organization_id:
            raise ValueError("Access denied: User not found in your organization.")
        
        # Remove user from project
        updated_user = await UserRepository.remove_from_project(user_id, project_id)
        return {"success": True, "user": updated_user}
    
    @staticmethod
    async def update_user_org_roles(
        user_id: str, 
        roles: List[str],
        admin_organization_id: str
    ) -> dict:
        """Update user's organization-level roles.
        
        Args:
            user_id: ID of user to update
            roles: New list of organization roles
            admin_organization_id: Organization ID of admin making the request
            
        Returns:
            dict: Success response with updated user data
        """
        # Get user and validate organization
        user = await UserRepository.get_by_id(user_id)
        if not user or user.organization_id != admin_organization_id:
            raise ValueError("Access denied: User not found in your organization.")
        
        # Update organization roles
        updated_user = await UserRepository.update_org_roles(user_id, roles)
        return {"success": True, "user": updated_user}
    
    @staticmethod
    async def get_organization_users(organization_id: str) -> List:
        """Get all users in an organization.
        
        Args:
            organization_id: Organization ID
            
        Returns:
            List of users in the organization
        """
        return await UserRepository.get_by_organization(organization_id)
    
    @staticmethod
    async def get_project_users(project_id: str, admin_organization_id: str) -> List:
        """Get all users assigned to a project.
        
        Args:
            project_id: Project ID
            admin_organization_id: Organization ID for access control
            
        Returns:
            List of users assigned to the project
        """
        # Validate project belongs to admin's organization
        project = await ProjectRepository.get_by_id(project_id)
        if not project or project.organization_id != admin_organization_id:
            raise ValueError("Access denied: Project not found in your organization.")
        
        return await UserRepository.get_by_project(project_id)
    
    @staticmethod
    async def deactivate_user(user_id: str, admin_organization_id: str) -> dict:
        """Deactivate a user account.
        
        Args:
            user_id: ID of user to deactivate
            admin_organization_id: Organization ID of admin making the request
            
        Returns:
            dict: Success response
        """
        # Get user and validate organization
        user = await UserRepository.get_by_id(user_id)
        if not user or user.organization_id != admin_organization_id:
            raise ValueError("Access denied: User not found in your organization.")
        
        # Deactivate user
        updated_user = await UserRepository.deactivate_user(user_id)
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
        # Get user and validate organization
        user = await UserRepository.get_by_id(user_id)
        if not user or user.organization_id != admin_organization_id:
            raise ValueError("Access denied: User not found in your organization.")
        
        # Activate user
        updated_user = await UserRepository.activate_user(user_id)
        return {"success": True, "user": updated_user}
    
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
        
        # Check project role
        if required_project_role and project_id:
            if not user.has_project_role(project_id, required_project_role):
                return {"has_permission": False, "reason": f"Missing project role: {required_project_role}"}
        
        return {"has_permission": True, "user": user} 