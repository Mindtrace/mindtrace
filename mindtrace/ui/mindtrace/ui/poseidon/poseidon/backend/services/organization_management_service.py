"""Organization Management service for super admin operations.

This module provides organization administration functionality including:
- Organization lifecycle operations (create, update, activate/deactivate)
- System-wide organization management
- Organization statistics and monitoring

This service is for super admin use only.
"""

from typing import List, Optional, Dict
from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
from poseidon.backend.core.exceptions import OrganizationNotFoundError


class OrganizationManagementService:
    """Service class for handling organization administration operations."""
    
    @staticmethod
    async def get_all_organizations() -> List:
        """Get all organizations in the system (super admin only).
        
        Returns:
            List of all organizations in the system
        """
        return await OrganizationRepository.get_all()
    
    @staticmethod
    async def create_organization(
        name: str,
        description: str = "",
        subscription_plan: str = "basic",
        max_users: int = 50,
        max_projects: int = 10
    ) -> dict:
        """Create a new organization.
        
        Args:
            name: Organization name
            description: Organization description
            subscription_plan: Subscription plan (basic, premium, enterprise)
            max_users: Maximum number of users allowed
            max_projects: Maximum number of projects allowed
            
        Returns:
            dict: Success response with created organization data
        """
        try:
            org_data = {
                "name": name,
                "description": description,
                "subscription_plan": subscription_plan,
                "max_users": max_users,
                "max_projects": max_projects,
                "is_active": True
            }
            
            new_org = await OrganizationRepository.create(org_data)
            return {"success": True, "organization": new_org}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def update_organization(organization_id: str, update_data: Dict) -> dict:
        """Update an existing organization.
        
        Args:
            organization_id: Organization ID to update
            update_data: Dictionary containing fields to update
            
        Returns:
            dict: Success response with updated organization data
        """
        try:
            # Get organization and validate
            org = await OrganizationRepository.get_by_id(organization_id)
            if not org:
                raise OrganizationNotFoundError("Organization not found.")
            
            # Update organization
            updated_org = await OrganizationRepository.update(organization_id, update_data)
            return {"success": True, "organization": updated_org}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def deactivate_organization(organization_id: str) -> dict:
        """Deactivate an organization.
        
        Args:
            organization_id: Organization ID to deactivate
            
        Returns:
            dict: Success response
        """
        try:
            # Get organization and validate
            org = await OrganizationRepository.get_by_id(organization_id)
            if not org:
                raise OrganizationNotFoundError("Organization not found.")
            
            # Deactivate organization
            updated_org = await OrganizationRepository.update(organization_id, {"is_active": False})
            return {"success": True, "organization": updated_org}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def activate_organization(organization_id: str) -> dict:
        """Activate an organization.
        
        Args:
            organization_id: Organization ID to activate
            
        Returns:
            dict: Success response
        """
        try:
            # Get organization and validate
            org = await OrganizationRepository.get_by_id(organization_id)
            if not org:
                raise OrganizationNotFoundError("Organization not found.")
            
            # Activate organization
            updated_org = await OrganizationRepository.update(organization_id, {"is_active": True})
            return {"success": True, "organization": updated_org}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def get_organization_stats(organization_id: str) -> dict:
        """Get statistics for a specific organization.
        
        Args:
            organization_id: Organization ID
            
        Returns:
            dict: Organization statistics
        """
        try:
            from poseidon.backend.database.repositories.user_repository import UserRepository
            from poseidon.backend.database.repositories.project_repository import ProjectRepository
            
            # Get organization
            org = await OrganizationRepository.get_by_id(organization_id)
            if not org:
                raise OrganizationNotFoundError("Organization not found.")
            
            # Get user count
            users = await UserRepository.get_by_organization(organization_id)
            active_users = await UserRepository.get_active_by_organization(organization_id)
            
            # Get project count
            try:
                projects = await ProjectRepository.get_by_organization(organization_id)
                project_count = len(projects)
            except:
                project_count = 0
            
            return {
                "success": True,
                "stats": {
                    "total_users": len(users),
                    "active_users": len(active_users),
                    "total_projects": project_count,
                    "subscription_plan": org.subscription_plan,
                    "max_users": org.max_users,
                    "max_projects": org.max_projects,
                    "usage_percentage": {
                        "users": (len(users) / org.max_users * 100) if org.max_users > 0 else 0,
                        "projects": (project_count / org.max_projects * 100) if org.max_projects > 0 else 0
                    }
                }
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def get_system_stats() -> dict:
        """Get system-wide statistics.
        
        Returns:
            dict: System statistics
        """
        try:
            from poseidon.backend.database.repositories.user_repository import UserRepository
            
            # Get all organizations
            all_orgs = await OrganizationRepository.get_all()
            active_orgs = await OrganizationRepository.get_all_active()
            
            # Get all users
            all_users = await UserRepository.get_all_users()
            
            return {
                "success": True,
                "stats": {
                    "total_organizations": len(all_orgs),
                    "active_organizations": len(active_orgs),
                    "total_users": len(all_users),
                    "system_status": "operational"
                }
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)} 