"""License Service

Business logic layer for project license management.
Handles license operations with proper validation and security.
"""

from datetime import datetime, UTC, timedelta
from typing import List, Optional, Dict, Any

from ..database.repositories.license_repository import LicenseRepository
from ..database.repositories.user_repository import UserRepository
from ..database.repositories.project_repository import ProjectRepository
from ..database.repositories.organization_repository import OrganizationRepository
from ..database.models.enums import OrgRole, LicenseStatus
from ...state.models import LicenseData


class LicenseService:
    """Service for license management operations"""
    
    @staticmethod
    def _convert_license_to_data(license) -> LicenseData:
        """Convert database license model to LicenseData for UI"""
        return LicenseData(
            id=str(license.id),
            license_key=license.license_key,
            project_id=str(license.project.id) if license.project else "",
            project_name=license.project.name if license.project else "Unknown Project",
            organization_id=str(license.organization.id) if license.organization else "",
            organization_name=license.organization.name if license.organization else "Unknown Organization",
            status=license.status,
            status_display=license.status_display,
            issued_at=license.issued_at,
            expires_at=license.expires_at,
            days_until_expiry=license.days_until_expiry,
            is_valid=license.is_valid,
            notes=license.notes,
            issued_by=license.issued_by.username if license.issued_by else "Unknown"
        )
    
    @staticmethod
    async def issue_license(
        project_id: str,
        expires_at: datetime,
        admin_user_id: str,
        notes: str = ""
    ) -> Dict[str, Any]:
        """Issue a new license for a project
        
        Args:
            project_id: ID of project to license
            expires_at: License expiration date
            admin_user_id: ID of super admin issuing the license
            notes: Optional notes about the license
            
        Returns:
            Result dictionary with success status and data/error
        """
        try:
            # Validate super admin privileges
            if not await LicenseService._validate_super_admin(admin_user_id):
                return {"success": False, "error": "Super admin privileges required"}
            
            # Validate project exists
            project = await ProjectRepository.get_by_id(project_id)
            if not project:
                return {"success": False, "error": "Project not found"}
            
            # Fetch organization link
            await project.fetch_link("organization")
            if not project.organization:
                return {"success": False, "error": "Project organization not found"}
            
            # Check if project already has an active license
            existing_license = await LicenseRepository.get_by_project(project_id)
            if existing_license and existing_license.is_valid:
                return {
                    "success": False, 
                    "error": f"Project already has an active license (expires: {existing_license.expires_at.strftime('%Y-%m-%d')})"
                }
            
            # Validate expiration date
            if expires_at <= datetime.now(UTC):
                return {"success": False, "error": "Expiration date must be in the future"}
            
            # Create the license
            license = await LicenseRepository.create_license(
                project_id=project_id,
                issued_by_user_id=admin_user_id,
                organization_id=str(project.organization.id),
                expires_at=expires_at,
                notes=notes
            )
            
            # Fetch all links for return data
            await license.fetch_all_links()
            
            return {
                "success": True,
                "license": {
                    "id": str(license.id),
                    "license_key": license.license_key,
                    "project_name": license.project.name if license.project else "Unknown",
                    "expires_at": license.expires_at,
                    "status": license.status
                }
            }
            
        except Exception as e:
            return {"success": False, "error": f"Failed to issue license: {str(e)}"}
    
    @staticmethod
    async def renew_license(
        license_id: str,
        new_expires_at: datetime,
        admin_user_id: str
    ) -> Dict[str, Any]:
        """Renew an existing license
        
        Args:
            license_id: ID of license to renew
            new_expires_at: New expiration date
            admin_user_id: ID of super admin renewing the license
            
        Returns:
            Result dictionary with success status and data/error
        """
        try:
            # Validate super admin privileges
            if not await LicenseService._validate_super_admin(admin_user_id):
                return {"success": False, "error": "Super admin privileges required"}
            
            # Validate license exists
            license = await LicenseRepository.get_by_id(license_id)
            if not license:
                return {"success": False, "error": "License not found"}
            
            # Validate expiration date
            if new_expires_at <= datetime.now(UTC):
                return {"success": False, "error": "Expiration date must be in the future"}
            
            # Renew the license
            success = await LicenseRepository.renew_license(
                license_id=license_id,
                new_expires_at=new_expires_at,
                renewed_by_user_id=admin_user_id
            )
            
            if success:
                # Fetch updated license data
                updated_license = await LicenseRepository.get_by_id(license_id)
                await updated_license.fetch_all_links()
                
                return {
                    "success": True,
                    "license": {
                        "id": str(updated_license.id),
                        "license_key": updated_license.license_key,
                        "project_name": updated_license.project.name if updated_license.project else "Unknown",
                        "expires_at": updated_license.expires_at,
                        "status": updated_license.status
                    }
                }
            else:
                return {"success": False, "error": "Failed to renew license"}
                
        except Exception as e:
            return {"success": False, "error": f"Failed to renew license: {str(e)}"}
    
    @staticmethod
    async def cancel_license(
        license_id: str,
        admin_user_id: str
    ) -> Dict[str, Any]:
        """Cancel a license
        
        Args:
            license_id: ID of license to cancel
            admin_user_id: ID of super admin cancelling the license
            
        Returns:
            Result dictionary with success status and data/error
        """
        try:
            # Validate super admin privileges
            if not await LicenseService._validate_super_admin(admin_user_id):
                return {"success": False, "error": "Super admin privileges required"}
            
            # Validate license exists
            license = await LicenseRepository.get_by_id(license_id)
            if not license:
                return {"success": False, "error": "License not found"}
            
            # Cancel the license
            success = await LicenseRepository.cancel_license(license_id)
            
            if success:
                return {"success": True, "message": "License cancelled successfully"}
            else:
                return {"success": False, "error": "Failed to cancel license"}
                
        except Exception as e:
            return {"success": False, "error": f"Failed to cancel license: {str(e)}"}
    
    @staticmethod
    async def get_organization_licenses(
        organization_id: str,
        admin_user_id: str
    ) -> Dict[str, Any]:
        """Get all licenses for an organization
        
        Args:
            organization_id: Organization ID
            admin_user_id: ID of requesting user
            
        Returns:
            Result dictionary with success status and licenses data
        """
        try:
            # Get requesting user to check privileges
            admin_user = await UserRepository.get_by_id(admin_user_id)
            if not admin_user:
                return {"success": False, "error": "User not found"}
            
            # Check access permissions
            if admin_user.org_role == OrgRole.SUPER_ADMIN:
                # Super admin can see all organization licenses
                licenses = await LicenseRepository.get_by_organization(organization_id)
            elif admin_user.org_role == OrgRole.ADMIN:
                # Regular admin can only see their own organization's licenses
                await admin_user.fetch_link("organization")
                if not admin_user.organization or str(admin_user.organization.id) != organization_id:
                    return {"success": False, "error": "Access denied: Can only view your organization's licenses"}
                licenses = await LicenseRepository.get_by_organization(organization_id)
            else:
                return {"success": False, "error": "Admin privileges required"}
            
            # Format license data for UI
            license_data = [LicenseService._convert_license_to_data(license) for license in licenses]
            
            return {"success": True, "licenses": license_data}
            
        except Exception as e:
            return {"success": False, "error": f"Failed to get licenses: {str(e)}"}
    
    @staticmethod
    async def get_all_licenses(admin_user_id: str) -> Dict[str, Any]:
        """Get all licenses across all organizations (super admin only)
        
        Args:
            admin_user_id: ID of super admin requesting data
            
        Returns:
            Result dictionary with success status and licenses data
        """
        try:
            # Validate super admin privileges
            if not await LicenseService._validate_super_admin(admin_user_id):
                return {"success": False, "error": "Super admin privileges required"}
            
            # Get all licenses
            licenses = await LicenseRepository.get_all()
            
            # Format license data for UI
            license_data = [LicenseService._convert_license_to_data(license) for license in licenses]
            
            return {"success": True, "licenses": license_data}
            
        except Exception as e:
            return {"success": False, "error": f"Failed to get licenses: {str(e)}"}
    
    @staticmethod
    async def validate_project_license(project_id: str) -> bool:
        """Validate if a project has a valid license for access control
        
        Args:
            project_id: Project ID to validate
            
        Returns:
            True if project has valid license, False otherwise
        """
        try:
            return await LicenseRepository.validate_project_access(project_id)
        except:
            return False
    
    @staticmethod
    async def get_license_stats(
        organization_id: Optional[str] = None,
        admin_user_id: str = None
    ) -> Dict[str, Any]:
        """Get license statistics
        
        Args:
            organization_id: Optional organization ID to filter stats
            admin_user_id: ID of requesting user
            
        Returns:
            Result dictionary with success status and stats data
        """
        try:
            if admin_user_id:
                # Validate user privileges if provided
                admin_user = await UserRepository.get_by_id(admin_user_id)
                if not admin_user or admin_user.org_role not in (OrgRole.ADMIN, OrgRole.SUPER_ADMIN):
                    return {"success": False, "error": "Admin privileges required"}
                
                # Regular admins can only see their own organization stats
                if admin_user.org_role == OrgRole.ADMIN:
                    await admin_user.fetch_link("organization")
                    if admin_user.organization:
                        organization_id = str(admin_user.organization.id)
                    else:
                        return {"success": False, "error": "User organization not found"}
            
            stats = await LicenseRepository.get_license_stats(organization_id)
            return {"success": True, "stats": stats}
            
        except Exception as e:
            return {"success": False, "error": f"Failed to get license stats: {str(e)}"}
    
    @staticmethod
    async def mark_expired_licenses() -> Dict[str, Any]:
        """Mark expired licenses as expired (maintenance operation)
        
        Returns:
            Result dictionary with success status and count of updated licenses
        """
        try:
            count = await LicenseRepository.mark_expired_licenses()
            return {"success": True, "expired_count": count}
        except Exception as e:
            return {"success": False, "error": f"Failed to mark expired licenses: {str(e)}"}
    
    @staticmethod
    async def get_expiring_licenses(
        days: int = 30,
        admin_user_id: str = None
    ) -> Dict[str, Any]:
        """Get licenses expiring within specified days
        
        Args:
            days: Number of days to look ahead
            admin_user_id: Optional admin user ID for filtering
            
        Returns:
            Result dictionary with success status and expiring licenses
        """
        try:
            licenses = await LicenseRepository.get_expiring_soon(days)
            
            # Filter by organization if regular admin
            if admin_user_id:
                admin_user = await UserRepository.get_by_id(admin_user_id)
                if admin_user and admin_user.org_role == OrgRole.ADMIN:
                    await admin_user.fetch_link("organization")
                    if admin_user.organization:
                        org_id = str(admin_user.organization.id)
                        licenses = [lic for lic in licenses if str(lic.organization.id) == org_id]
            
            # Format license data
            license_data = [LicenseService._convert_license_to_data(license) for license in licenses]
            
            return {"success": True, "expiring_licenses": license_data}
            
        except Exception as e:
            return {"success": False, "error": f"Failed to get expiring licenses: {str(e)}"}
    
    @staticmethod
    async def _validate_super_admin(admin_user_id: str) -> bool:
        """Validate super admin privileges
        
        Args:
            admin_user_id: User ID to validate
            
        Returns:
            True if user is super admin, False otherwise
        """
        try:
            admin_user = await UserRepository.get_by_id(admin_user_id)
            return admin_user and admin_user.org_role == OrgRole.SUPER_ADMIN
        except:
            return False