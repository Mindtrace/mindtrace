"""License Repository

Data access layer for project license operations.
Follows the established repository pattern with organization-scoped access.
"""

from datetime import datetime, UTC, timedelta
from typing import List, Optional, Dict, Any
import secrets
import string

from beanie import PydanticObjectId

from ..models.project_license import ProjectLicense
from ..models.enums import LicenseStatus
from ..models.user import User
from ..models.project import Project
from ..models.organization import Organization


class LicenseRepository:
    """Repository for project license data access operations"""
    
    @staticmethod
    async def create_license(
        project_id: str,
        issued_by_user_id: str,
        organization_id: str,
        expires_at: datetime,
        notes: str = ""
    ) -> ProjectLicense:
        """Create a new project license
        
        Args:
            project_id: ID of the project to license
            issued_by_user_id: ID of super admin issuing the license
            organization_id: ID of the organization
            expires_at: License expiration date
            notes: Optional notes about the license
            
        Returns:
            Created ProjectLicense instance
        """
        # Generate unique license key
        license_key = LicenseRepository._generate_license_key()
        
        # Create license
        license_data = ProjectLicense(
            project=PydanticObjectId(project_id),
            license_key=license_key,
            status=LicenseStatus.ACTIVE,
            issued_at=datetime.now(UTC),
            expires_at=expires_at,
            issued_by=PydanticObjectId(issued_by_user_id),
            organization=PydanticObjectId(organization_id),
            notes=notes
        )
        
        return await license_data.create()
    
    @staticmethod
    async def get_by_id(license_id: str) -> Optional[ProjectLicense]:
        """Get license by ID"""
        try:
            return await ProjectLicense.get(PydanticObjectId(license_id))
        except:
            return None
    
    @staticmethod
    async def get_by_project(project_id: str) -> Optional[ProjectLicense]:
        """Get active license for a project
        
        Args:
            project_id: Project ID to get license for
            
        Returns:
            Active ProjectLicense or None if no active license
        """
        return await ProjectLicense.find_one({
            "project.$id": PydanticObjectId(project_id),
            "status": LicenseStatus.ACTIVE
        })
    
    @staticmethod
    async def get_by_license_key(license_key: str) -> Optional[ProjectLicense]:
        """Get license by license key"""
        return await ProjectLicense.find_one({"license_key": license_key})
    
    @staticmethod
    async def get_by_organization(organization_id: str) -> List[ProjectLicense]:
        """Get all licenses for an organization
        
        Args:
            organization_id: Organization ID
            
        Returns:
            List of ProjectLicense instances
        """
        licenses = await ProjectLicense.find({
            "organization.$id": PydanticObjectId(organization_id)
        }).to_list()
        
        # Fetch all related links for better performance
        for license in licenses:
            await license.fetch_all_links()
        
        return licenses
    
    @staticmethod
    async def get_all() -> List[ProjectLicense]:
        """Get all licenses across all organizations (super admin view)
        
        Returns:
            List of all ProjectLicense instances
        """
        licenses = await ProjectLicense.find().to_list()
        
        # Fetch all related links for better performance
        for license in licenses:
            await license.fetch_all_links()
        
        return licenses
    
    @staticmethod
    async def update_status(license_id: str, status: LicenseStatus) -> bool:
        """Update license status
        
        Args:
            license_id: License ID to update
            status: New license status
            
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            license = await ProjectLicense.get(PydanticObjectId(license_id))
            if license:
                license.status = status
                await license.save()
                return True
            return False
        except Exception as e:
            print(f"Error updating license status: {e}")
            return False
    
    @staticmethod
    async def renew_license(
        license_id: str,
        new_expires_at: datetime,
        renewed_by_user_id: str
    ) -> bool:
        """Renew an existing license
        
        Args:
            license_id: License ID to renew
            new_expires_at: New expiration date
            renewed_by_user_id: ID of super admin renewing the license
            
        Returns:
            True if renewed successfully, False otherwise
        """
        try:
            license = await ProjectLicense.get(PydanticObjectId(license_id))
            if license:
                license.expires_at = new_expires_at
                license.status = LicenseStatus.ACTIVE  # Reactivate if needed
                # Don't update issued_by for renewal - keep original issuer
                await license.save()
                return True
            return False
        except Exception as e:
            return False
    
    @staticmethod
    async def cancel_license(license_id: str) -> bool:
        """Cancel a license (set status to cancelled)
        
        Args:
            license_id: License ID to cancel
            
        Returns:
            True if cancelled successfully, False otherwise
        """
        return await LicenseRepository.update_status(license_id, LicenseStatus.CANCELLED)
    
    @staticmethod
    async def get_expiring_soon(days: int = 30) -> List[ProjectLicense]:
        """Get licenses expiring within specified days
        
        Args:
            days: Number of days to look ahead for expiring licenses
            
        Returns:
            List of licenses expiring soon
        """
        cutoff_date = datetime.now(UTC) + timedelta(days=days)
        
        licenses = await ProjectLicense.find({
            "status": LicenseStatus.ACTIVE,
            "expires_at": {"$lte": cutoff_date}
        }).to_list()
        
        # Fetch all related links
        for license in licenses:
            await license.fetch_all_links()
        
        return licenses
    
    @staticmethod
    async def get_expired_licenses() -> List[ProjectLicense]:
        """Get all expired licenses that are still marked as active
        
        Returns:
            List of expired licenses
        """
        now = datetime.now(UTC)
        
        licenses = await ProjectLicense.find({
            "status": LicenseStatus.ACTIVE,
            "expires_at": {"$lt": now}
        }).to_list()
        
        # Fetch all related links
        for license in licenses:
            await license.fetch_all_links()
        
        return licenses
    
    @staticmethod
    async def mark_expired_licenses() -> int:
        """Mark expired licenses as expired status
        
        Returns:
            Number of licenses marked as expired
        """
        now = datetime.now(UTC)
        
        expired_licenses = await ProjectLicense.find({
            "status": LicenseStatus.ACTIVE,
            "expires_at": {"$lt": now}
        }).to_list()
        
        count = 0
        for license in expired_licenses:
            license.status = LicenseStatus.EXPIRED
            await license.save()
            count += 1
        
        return count
    
    @staticmethod
    async def get_license_stats(organization_id: Optional[str] = None) -> Dict[str, Any]:
        """Get license statistics
        
        Args:
            organization_id: Optional organization ID to filter stats
            
        Returns:
            Dictionary with license statistics
        """
        query = {}
        if organization_id:
            query["organization.$id"] = PydanticObjectId(organization_id)
        
        all_licenses = await ProjectLicense.find(query).to_list()
        
        total = len(all_licenses)
        active = len([lic for lic in all_licenses if lic.status == LicenseStatus.ACTIVE])
        expired = len([lic for lic in all_licenses if lic.status == LicenseStatus.EXPIRED])
        cancelled = len([lic for lic in all_licenses if lic.status == LicenseStatus.CANCELLED])
        
        # Count licenses expiring in next 30 days
        cutoff = datetime.now(UTC) + timedelta(days=30)
        expiring_soon = 0
        for lic in all_licenses:
            if lic.status == LicenseStatus.ACTIVE and lic.expires_at:
                # Ensure timezone-aware comparison
                expires = lic.expires_at
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=UTC)
                if expires <= cutoff:
                    expiring_soon += 1
        
        return {
            "total_licenses": total,
            "active_licenses": active,
            "expired_licenses": expired,
            "cancelled_licenses": cancelled,
            "expiring_soon": expiring_soon
        }
    
    @staticmethod
    def _generate_license_key() -> str:
        """Generate a unique license key
        
        Returns:
            Unique license key string
        """
        # Generate a 20-character alphanumeric license key
        alphabet = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(20))
    
    @staticmethod
    async def validate_project_access(project_id: str) -> bool:
        """Validate if a project has a valid license for full access
        
        Args:
            project_id: Project ID to check
            
        Returns:
            True if project has valid license, False otherwise
        """
        license = await LicenseRepository.get_by_project(project_id)
        if not license:
            return False
        
        return license.is_valid