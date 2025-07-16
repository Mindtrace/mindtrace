from poseidon.backend.database.models.model import Model
from poseidon.backend.core.config import settings
from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
from typing import Optional, List

backend = MongoMindtraceODMBackend(Model, db_uri=settings.MONGO_URI, db_name=settings.DB_NAME)

class ModelRepository:
    @staticmethod
    async def get_by_organization(organization_id: str) -> List[Model]:
        """Get all models for an organization"""
        await backend.initialize()
        return await backend.find({"organization_id": organization_id, "is_active": True})

    @staticmethod
    async def create(model_data: dict) -> Model:
        """Create a new model"""
        await backend.initialize()
        model = Model(**model_data)
        return await backend.insert(model)

    @staticmethod
    async def get_by_id(model_id: str) -> Optional[Model]:
        """Get model by ID"""
        await backend.initialize()
        try:
            return await backend.get(model_id)
        except:
            return None

    @staticmethod
    async def get_by_name(name: str, organization_id: str) -> Optional[Model]:
        """Get model by name within organization"""
        await backend.initialize()
        models = await backend.find({
            "name": name,
            "organization_id": organization_id,
            "is_active": True
        })
        return models[0] if models else None

    @staticmethod
    async def update(model: Model) -> Model:
        """Update a model"""
        await backend.initialize()
        model.update_timestamp()
        return await backend.update(model)

    @staticmethod
    async def delete(model_id: str) -> bool:
        """Soft delete a model (mark as inactive)"""
        await backend.initialize()
        try:
            model = await backend.get(model_id)
            if model:
                model.is_active = False
                model.update_timestamp()
                await backend.update(model)
                return True
        except:
            pass
        return False

    @staticmethod
    async def get_all_active() -> List[Model]:
        """Get all active models across all organizations (for super admin)"""
        await backend.initialize()
        return await backend.find({"is_active": True})

    @staticmethod
    async def get_by_type(model_type: str, organization_id: str) -> List[Model]:
        """Get models by type within organization"""
        await backend.initialize()
        return await backend.find({
            "type": model_type,
            "organization_id": organization_id,
            "is_active": True
        })

    @staticmethod
    async def search_models(query: str, organization_id: str) -> List[Model]:
        """Search models by name or description"""
        await backend.initialize()
        return await backend.find({
            "$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"description": {"$regex": query, "$options": "i"}}
            ],
            "organization_id": organization_id,
            "is_active": True
        })

    @staticmethod
    async def get_latest_version(name: str, organization_id: str) -> Optional[Model]:
        """Get the latest version of a model"""
        await backend.initialize()
        models = await backend.find({
            "name": name,
            "organization_id": organization_id,
            "is_active": True
        })
        
        if not models:
            return None
            
        # Sort by version (assuming semantic versioning)
        sorted_models = sorted(models, key=lambda x: x.version, reverse=True)
        return sorted_models[0]

    @staticmethod
    async def get_validated_models(organization_id: str) -> List[Model]:
        """Get only validated models for an organization"""
        await backend.initialize()
        return await backend.find({
            "organization_id": organization_id,
            "is_active": True,
            "validation_status": "validated"
        })