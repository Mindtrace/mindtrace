from poseidon.backend.database.models.model_deployment import ModelDeployment
from poseidon.backend.database.models.model import Model
from poseidon.backend.database.models.organization import Organization
from poseidon.backend.database.init import initialize_database
from typing import Optional, List

class ModelDeploymentRepository:
    @staticmethod
    async def _ensure_init():
        """Ensure database is initialized before operations"""
        await initialize_database()

    @staticmethod
    async def create(deployment_data: dict) -> ModelDeployment:
        """Create a new model deployment"""
        await ModelDeploymentRepository._ensure_init()
        
        # Convert model_id to Link[Model] if provided
        if "model_id" in deployment_data:
            model_id = deployment_data.pop("model_id")
            model = await Model.get(model_id)
            deployment_data["model"] = model
        
        # Convert organization_id to Link[Organization] if provided
        if "organization_id" in deployment_data:
            org_id = deployment_data.pop("organization_id")
            organization = await Organization.get(org_id)
            deployment_data["organization"] = organization
        
        # Convert project_id to Link[Project] if provided  
        if "project_id" in deployment_data:
            from poseidon.backend.database.models.project import Project
            project_id = deployment_data.pop("project_id")
            project = await Project.get(project_id)
            deployment_data["project"] = project
        
        # Convert created_by_id to Link[User] if provided
        if "created_by_id" in deployment_data:
            from poseidon.backend.database.models.user import User
            user_id = deployment_data.pop("created_by_id")
            user = await User.get(user_id)
            deployment_data["created_by"] = user
        
        deployment = ModelDeployment(**deployment_data)
        return await deployment.insert()

    @staticmethod
    async def get_by_id(deployment_id: str) -> Optional[ModelDeployment]:
        """Get deployment by ID"""
        await ModelDeploymentRepository._ensure_init()
        try:
            deployment = await ModelDeployment.get(deployment_id)
            if deployment:
                await deployment.fetch_all_links()
            return deployment
        except:
            return None

    @staticmethod
    async def get_by_organization(organization_id: str) -> List[ModelDeployment]:
        """Get all deployments for an organization"""
        await ModelDeploymentRepository._ensure_init()
        try:
            organization = await Organization.get(organization_id)
            if not organization:
                return []
            deployments = await ModelDeployment.find(ModelDeployment.organization.id == organization.id).to_list()
            for deployment in deployments:
                await deployment.fetch_all_links()
            return deployments
        except:
            return []

    @staticmethod
    async def get_all() -> List[ModelDeployment]:
        """Get all deployments"""
        await ModelDeploymentRepository._ensure_init()
        deployments = await ModelDeployment.find_all().to_list()
        for deployment in deployments:
            await deployment.fetch_all_links()
        return deployments

    @staticmethod
    async def get_active_by_organization(organization_id: str) -> List[ModelDeployment]:
        """Get active deployments for an organization"""
        await ModelDeploymentRepository._ensure_init()
        try:
            organization = await Organization.get(organization_id)
            if not organization:
                return []
            deployments = await ModelDeployment.find(
                ModelDeployment.organization.id == organization.id,
                ModelDeployment.deployment_status == "deployed"
            ).to_list()
            for deployment in deployments:
                await deployment.fetch_all_links()
            return deployments
        except:
            return []

    @staticmethod
    async def get_by_model_id(model_id: str) -> List[ModelDeployment]:
        """Get deployments by model ID"""
        await ModelDeploymentRepository._ensure_init()
        try:
            model = await Model.get(model_id)
            if not model:
                return []
            deployments = await ModelDeployment.find(ModelDeployment.model.id == model.id).to_list()
            for deployment in deployments:
                await deployment.fetch_all_links()
            return deployments
        except:
            return []

    @staticmethod
    async def update(deployment_id: str, update_data: dict) -> Optional[ModelDeployment]:
        """Update deployment"""
        await ModelDeploymentRepository._ensure_init()
        try:
            deployment = await ModelDeployment.get(deployment_id)
            if deployment:
                for key, value in update_data.items():
                    if hasattr(deployment, key):
                        setattr(deployment, key, value)
                deployment.update_timestamp() 
                await deployment.save()
                return deployment
        except:
            pass
        return None

    @staticmethod
    async def delete(deployment_id: str) -> bool:
        """Delete deployment"""
        await ModelDeploymentRepository._ensure_init()
        try:
            deployment = await ModelDeployment.get(deployment_id)
            if deployment:
                await deployment.delete()
                return True
        except:
            pass
        return False

    @staticmethod
    async def deactivate_previous(model_id: str) -> bool:
        """Deactivate previous deployments for a model"""
        await ModelDeploymentRepository._ensure_init()
        try:
            model = await Model.get(model_id)
            if not model:
                return False
            
            # Find active deployments for this model
            deployments = await ModelDeployment.find(
                ModelDeployment.model.id == model.id,
                ModelDeployment.deployment_status == "deployed"
            ).to_list()
            
            # Deactivate them
            for deployment in deployments:
                deployment.deployment_status = "inactive"
                await deployment.save()
            
            return True
        except:
            return False