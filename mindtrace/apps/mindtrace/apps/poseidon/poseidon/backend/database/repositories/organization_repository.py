from poseidon.backend.database.models.organization import Organization
from poseidon.backend.database.init import initialize_database
from typing import Optional, List

class OrganizationRepository:
    @staticmethod
    async def _ensure_init():
        """Ensure database is initialized before operations"""
        await initialize_database()

    @staticmethod
    async def create(org_data: dict) -> Organization:
        """Create a new organization"""
        await OrganizationRepository._ensure_init()
        organization = Organization(**org_data)
        return await organization.insert()

    @staticmethod
    async def get_by_id(org_id: str) -> Optional[Organization]:
        """Get organization by ID"""
        await OrganizationRepository._ensure_init()
        try:
            return await Organization.get(org_id)
        except:
            return None

    @staticmethod
    async def get_by_name(name: str) -> Optional[Organization]:
        """Get organization by name"""
        await OrganizationRepository._ensure_init()
        return await Organization.find_one(Organization.name == name)

    @staticmethod
    async def get_all() -> List[Organization]:
        """Get all organizations"""
        await OrganizationRepository._ensure_init()
        return await Organization.find_all().to_list()

    @staticmethod
    async def update(org_id: str, update_data: dict) -> Optional[Organization]:
        """Update organization"""
        await OrganizationRepository._ensure_init()
        try:
            organization = await Organization.get(org_id)
            if organization:
                for key, value in update_data.items():
                    if hasattr(organization, key):
                        setattr(organization, key, value)
                organization.update_timestamp()
                await organization.save()
                return organization
        except:
            pass
        return None

    @staticmethod
    async def delete(org_id: str) -> bool:
        """Delete organization"""
        await OrganizationRepository._ensure_init()
        try:
            organization = await Organization.get(org_id)
            if organization:
                await organization.delete()
                return True
        except:
            pass
        return False

    @staticmethod
    async def get_active_organizations() -> List[Organization]:
        """Get all active organizations"""
        await OrganizationRepository._ensure_init()
        return await Organization.find(Organization.is_active == True).to_list()

    @staticmethod
    async def get_all_active() -> List[Organization]:
        """Alias for get_active_organizations for consistency"""
        return await OrganizationRepository.get_active_organizations()

    @staticmethod
    async def increment_user_count(org_id: str) -> Optional[Organization]:
        """Increment user count for an organization"""
        await OrganizationRepository._ensure_init()
        try:
            organization = await Organization.get(org_id)
            if organization:
                organization.user_count += 1
                await organization.save()
                return organization
        except:
            pass
        return None

    @staticmethod
    async def decrement_user_count(org_id: str) -> Optional[Organization]:
        """Decrement user count for an organization"""
        await OrganizationRepository._ensure_init()
        try:
            organization = await Organization.get(org_id)
            if organization and organization.user_count > 0:
                organization.user_count -= 1
                await organization.save()
                return organization
        except:
            pass
        return None 