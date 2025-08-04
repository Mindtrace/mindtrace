from poseidon.backend.database.models.model import Model
from poseidon.backend.database.models.organization import Organization
from poseidon.backend.database.init import initialize_database
from typing import Optional, List

class ModelRepository:
    @staticmethod
    async def _ensure_init():
        """Ensure database is initialized before operations"""
        await initialize_database()

    @staticmethod
    async def create(model_data: dict) -> Model:
        """Create a new model"""
        await ModelRepository._ensure_init()
        
        # Convert organization_id to Link[Organization] if provided
        if "organization_id" in model_data:
            org_id = model_data.pop("organization_id")
            organization = await Organization.get(org_id)
            model_data["organization"] = organization
        
        # Convert created_by_id to Link[User] if provided
        if "created_by_id" in model_data:
            from poseidon.backend.database.models.user import User
            user_id = model_data.pop("created_by_id")
            user = await User.get(user_id)
            model_data["created_by"] = user
        
        # Convert project_id to Link[Project] if provided  
        if "project_id" in model_data:
            from poseidon.backend.database.models.project import Project
            project_id = model_data.pop("project_id")
            project = await Project.get(project_id)
            model_data["project"] = project
        
        model = Model(**model_data)
        return await model.insert()

    @staticmethod
    async def get_by_id(model_id: str) -> Optional[Model]:
        """Get model by ID"""
        await ModelRepository._ensure_init()
        try:
            model = await Model.get(model_id)
            if model:
                await model.fetch_all_links()
            return model
        except:
            return None

    @staticmethod
    async def get_by_name(name: str, organization_id: str) -> Optional[Model]:
        """Get model by name within organization"""
        await ModelRepository._ensure_init()
        try:
            organization = await Organization.get(organization_id)
            if not organization:
                return None
            model = await Model.find_one(
                Model.name == name,
                Model.organization.id == organization.id
            )
            if model:
                await model.fetch_all_links()
            return model
        except:
            return None

    @staticmethod
    async def get_by_organization(organization_id: str) -> List[Model]:
        """Get all models for an organization"""
        await ModelRepository._ensure_init()
        try:
            organization = await Organization.get(organization_id)
            if not organization:
                return []
            models = await Model.find(Model.organization.id == organization.id).to_list()
            for model in models:
                await model.fetch_all_links()
            return models
        except:
            return []

    @staticmethod
    async def get_all() -> List[Model]:
        """Get all models"""
        await ModelRepository._ensure_init()
        models = await Model.find_all().to_list()
        for model in models:
            await model.fetch_all_links()
        return models

    @staticmethod
    async def update(model_id: str, update_data: dict) -> Optional[Model]:
        """Update model"""
        await ModelRepository._ensure_init()
        try:
            model = await Model.get(model_id)
            if model:
                for key, value in update_data.items():
                    if hasattr(model, key):
                        setattr(model, key, value)
                model.update_timestamp()  
                await model.save()
                return model
        except:
            pass
        return None

    @staticmethod
    async def delete(model_id: str) -> bool:
        """Delete model"""
        await ModelRepository._ensure_init()
        try:
            model = await Model.get(model_id)
            if model:
                await model.delete()
                return True
        except:
            pass
        return False