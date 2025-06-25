from poseidon.backend.database.models.organization import Organization
from poseidon.backend.core.config import settings
from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
from typing import Optional, List

backend = MongoMindtraceODMBackend(Organization, db_uri=settings.MONGO_URI, db_name=settings.DB_NAME)

class OrganizationRepository:
    @staticmethod
    async def create_organization(org_data: dict) -> Organization:
        await backend.initialize()
        organization = Organization(**org_data)
        return await backend.insert(organization)
    
    @staticmethod
    async def get_by_id(org_id: str) -> Optional[Organization]:
        await backend.initialize()
        try:
            return await backend.get(org_id)
        except:
            return None
    
    @staticmethod
    async def get_by_name(name: str) -> Optional[Organization]:
        await backend.initialize()
        orgs = await backend.find({"name": name, "is_active": True})
        return orgs[0] if orgs else None
    
    @staticmethod
    async def get_all_active() -> List[Organization]:
        """Get all active organizations"""
        await backend.initialize()
        return await backend.find({"is_active": True})
    
    @staticmethod
    async def update_settings(org_id: str, settings: dict) -> Optional[Organization]:
        """Update organization settings"""
        await backend.initialize()
        org = await backend.get(org_id)
        if org:
            org.settings.update(settings)
            org.update_timestamp()
            return await backend.update(org_id, org.dict())
        return None
    
    @staticmethod
    async def update_subscription(org_id: str, plan: str, max_users: int = None, max_projects: int = None) -> Optional[Organization]:
        """Update organization subscription plan"""
        await backend.initialize()
        org = await backend.get(org_id)
        if org:
            org.subscription_plan = plan
            if max_users is not None:
                org.max_users = max_users
            if max_projects is not None:
                org.max_projects = max_projects
            org.update_timestamp()
            return await backend.update(org_id, org.dict())
        return None
    
    @staticmethod
    async def deactivate_organization(org_id: str) -> Optional[Organization]:
        """Deactivate organization"""
        await backend.initialize()
        org = await backend.get(org_id)
        if org:
            org.is_active = False
            org.update_timestamp()
            return await backend.update(org_id, org.dict())
        return None
    
    @staticmethod
    async def get_organizations_by_plan(plan: str) -> List[Organization]:
        """Get organizations by subscription plan"""
        await backend.initialize()
        return await backend.find({"subscription_plan": plan, "is_active": True}) 