"""Organization Management service for super admin operations.

This module provides organization administration functionality including:
- Organization lifecycle operations (create, update, activate/deactivate, delete)
- System-wide organization management
- Organization statistics and monitoring

SECURITY: All methods require super admin privileges and validate permissions at the service layer.
This provides defense-in-depth against privilege escalation attacks.

This service is for super admin use only.
"""

from typing import List, Dict
from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
from poseidon.backend.database.repositories.user_repository import UserRepository
from poseidon.backend.core.exceptions import OrganizationNotFoundError
from poseidon.backend.database.models.enums import SubscriptionPlan, OrgRole


class OrganizationManagementService:
    """Service class for handling organization administration operations.
    
    SECURITY: All methods validate super admin privileges to prevent privilege escalation.
    """
    
    @staticmethod
    async def _validate_super_admin(admin_user_id: str) -> bool:
        """Validate that the requesting user is a super admin.
        
        Args:
            admin_user_id: ID of the user making the request
            
        Returns:
            bool: True if user is super admin, False otherwise
            
        Raises:
            ValueError: If user is not found or not a super admin
        """
        if not admin_user_id:
            raise ValueError("Admin user ID is required")
            
        admin_user = await UserRepository.get_by_id(admin_user_id)
        if not admin_user:
            raise ValueError("Admin user not found")
            
        if admin_user.org_role != OrgRole.SUPER_ADMIN:
            raise ValueError("Super admin privileges required for organization management")
            
        return True
    
    @staticmethod
    async def get_all_organizations(admin_user_id: str) -> List:
        """Get all organizations in the system (super admin only).
        
        Args:
            admin_user_id: ID of the super admin making the request
            
        Returns:
            List of all organizations in the system
            
        Raises:
            ValueError: If user is not a super admin
        """
        await OrganizationManagementService._validate_super_admin(admin_user_id)
        return await OrganizationRepository.get_all()
    
    @staticmethod
    async def create_organization(
        admin_user_id: str,
        name: str,
        description: str = "",
        subscription_plan: SubscriptionPlan = SubscriptionPlan.BASIC,
        max_users: int = 50,
        max_projects: int = 10
    ) -> dict:
        """Create a new organization (super admin only).
        
        Args:
            admin_user_id: ID of the super admin making the request
            name: Organization name
            description: Organization description
            subscription_plan: Subscription plan (basic, premium, enterprise)
            max_users: Maximum number of users allowed
            max_projects: Maximum number of projects allowed
            
        Returns:
            dict: Success response with created organization data
            
        Raises:
            ValueError: If user is not a super admin
        """
        try:
            # Validate super admin privileges first
            await OrganizationManagementService._validate_super_admin(admin_user_id)
            
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
    async def update_organization(admin_user_id: str, organization_id: str, update_data: Dict) -> dict:
        """Update an existing organization (super admin only).
        
        Args:
            admin_user_id: ID of the super admin making the request
            organization_id: Organization ID to update
            update_data: Dictionary containing fields to update
            
        Returns:
            dict: Success response with updated organization data
            
        Raises:
            ValueError: If user is not a super admin
        """
        try:
            # Validate super admin privileges first
            await OrganizationManagementService._validate_super_admin(admin_user_id)
            
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
    async def deactivate_organization(admin_user_id: str, organization_id: str) -> dict:
        """Deactivate an organization (super admin only).
        
        Args:
            admin_user_id: ID of the super admin making the request
            organization_id: Organization ID to deactivate
            
        Returns:
            dict: Success response
            
        Raises:
            ValueError: If user is not a super admin
        """
        try:
            # Validate super admin privileges first
            await OrganizationManagementService._validate_super_admin(admin_user_id)
            
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
    async def activate_organization(admin_user_id: str, organization_id: str) -> dict:
        """Activate an organization (super admin only).
        
        Args:
            admin_user_id: ID of the super admin making the request
            organization_id: Organization ID to activate
            
        Returns:
            dict: Success response
            
        Raises:
            ValueError: If user is not a super admin
        """
        try:
            # Validate super admin privileges first
            await OrganizationManagementService._validate_super_admin(admin_user_id)
            
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
    async def delete_organization(admin_user_id: str, organization_id: str) -> dict:
        """Delete an organization (super admin only).
        
        SECURITY WARNING: This permanently deletes the organization and all associated data.
        Use with extreme caution.
        
        Args:
            admin_user_id: ID of the super admin making the request
            organization_id: Organization ID to delete
            
        Returns:
            dict: Success response
            
        Raises:
            ValueError: If user is not a super admin
        """
        try:
            # Validate super admin privileges first
            await OrganizationManagementService._validate_super_admin(admin_user_id)
            
            # Get organization and validate
            org = await OrganizationRepository.get_by_id(organization_id)
            if not org:
                raise OrganizationNotFoundError("Organization not found.")
            
            # Check if organization has users (safety check)
            users = await UserRepository.get_by_organization(organization_id)
            if users:
                return {"success": False, "error": f"Cannot delete organization with {len(users)} users. Deactivate first."}
            
            # Delete organization
            success = await OrganizationRepository.delete(organization_id)
            if success:
                return {"success": True, "message": "Organization deleted successfully"}
            else:
                return {"success": False, "error": "Failed to delete organization"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def get_organization_stats(admin_user_id: str, organization_id: str) -> dict:
        """Get statistics for a specific organization (super admin only).
        
        Args:
            admin_user_id: ID of the super admin making the request
            organization_id: Organization ID
            
        Returns:
            dict: Organization statistics
            
        Raises:
            ValueError: If user is not a super admin
        """
        try:
            # Validate super admin privileges first
            await OrganizationManagementService._validate_super_admin(admin_user_id)
            
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
    async def get_system_stats(admin_user_id: str) -> dict:
        """Get system-wide statistics (super admin only).
        
        Args:
            admin_user_id: ID of the super admin making the request
        
        Returns:
            dict: System statistics
            
        Raises:
            ValueError: If user is not a super admin
        """
        try:
            # Validate super admin privileges first
            await OrganizationManagementService._validate_super_admin(admin_user_id)
            
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