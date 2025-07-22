from poseidon.backend.database.models.organization import Organization
from poseidon.backend.core.config import settings
from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
from typing import Optional, List

backend = MongoMindtraceODMBackend(Organization, db_uri=settings.MONGO_URI, db_name=settings.DB_NAME)

class OrganizationRepository:
    @staticmethod
    async def create(org_data: dict) -> Organization:
        """Create a new organization"""
        await backend.initialize()
        organization = Organization(**org_data)
        return await backend.insert(organization)
    
    @staticmethod
    async def get_by_id(org_id: str) -> Optional[Organization]:
        """Get organization by ID"""
        await backend.initialize()
        try:
            return await backend.get(org_id)
        except:
            return None
    
    @staticmethod
    async def get_by_name(name: str) -> Optional[Organization]:
        """Get organization by name (active only)"""
        await backend.initialize()
        orgs = await backend.find({"name": name, "is_active": True})
        return orgs[0] if orgs else None
    
    @staticmethod
    async def get_all_active() -> List[Organization]:
        """Get all active organizations"""
        await backend.initialize()
        return await backend.find({"is_active": True})
    
    @staticmethod
    async def get_all() -> List[Organization]:
        """Get all organizations (active and inactive)"""
        await backend.initialize()
        return await backend.find({})
    
    @staticmethod
    async def update(org_id: str, update_data: dict) -> Optional[Organization]:
        """Update organization with arbitrary data"""
        await backend.initialize()
        try:
            org = await backend.get(org_id)
            if org:
                for key, value in update_data.items():
                    if hasattr(org, key):
                        setattr(org, key, value)
                org.update_timestamp()
                return await backend.update(org_id, org)
        except:
            pass
        return None
    
    @staticmethod
    async def get_by_plan(plan: str) -> List[Organization]:
        """Get organizations by subscription plan"""
        await backend.initialize()
        return await backend.find({"subscription_plan": plan, "is_active": True}) 