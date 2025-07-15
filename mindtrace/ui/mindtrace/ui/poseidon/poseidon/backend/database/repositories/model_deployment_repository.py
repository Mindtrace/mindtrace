from poseidon.backend.database.models.model_deployment import ModelDeployment
from poseidon.backend.core.config import settings
from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
from typing import Optional, List

backend = MongoMindtraceODMBackend(ModelDeployment, db_uri=settings.MONGO_URI, db_name=settings.DB_NAME)

class ModelDeploymentRepository:
    @staticmethod
    async def create(deployment_data: dict) -> ModelDeployment:
        """Create new deployment"""
        await backend.initialize()
        deployment = ModelDeployment(**deployment_data)
        return await backend.insert(deployment)

    @staticmethod
    async def get_active_by_organization(organization_id: str) -> List[ModelDeployment]:
        """Get active deployments for an organization"""
        await backend.initialize()
        return await backend.find({
            "organization_id": organization_id,
            "is_active": True
        })

    @staticmethod
    async def get_by_camera_id(camera_id: str) -> Optional[ModelDeployment]:
        """Get deployment for a specific camera"""
        await backend.initialize()
        deployments = await backend.find({
            "camera_ids": {"$in": [camera_id]},
            "is_active": True
        })
        return deployments[0] if deployments else None

    @staticmethod
    async def deactivate_previous(model_id: str) -> bool:
        """Deactivate previous deployments for a model"""
        await backend.initialize()
        try:
            deployments = await backend.find({
                "model_id": model_id,
                "is_active": True
            })
            
            for deployment in deployments:
                deployment.is_active = False
                deployment.update_timestamp()
                await backend.update(deployment)
            
            return True
        except:
            return False

    @staticmethod
    async def update_status(deployment_id: str, status: str) -> Optional[ModelDeployment]:
        """Update deployment status"""
        await backend.initialize()
        try:
            deployment = await backend.get(deployment_id)
            if deployment:
                deployment.update_status(status)
                return await backend.update(deployment)
        except:
            pass
        return None

    @staticmethod
    async def get_by_id(deployment_id: str) -> Optional[ModelDeployment]:
        """Get deployment by ID"""
        await backend.initialize()
        try:
            return await backend.get(deployment_id)
        except:
            return None

    @staticmethod
    async def get_by_model_id(model_id: str) -> List[ModelDeployment]:
        """Get all deployments for a model"""
        await backend.initialize()
        return await backend.find({
            "model_id": model_id,
            "is_active": True
        })

    @staticmethod
    async def get_deployed_models(organization_id: str) -> List[ModelDeployment]:
        """Get all deployed models for an organization"""
        await backend.initialize()
        return await backend.find({
            "organization_id": organization_id,
            "deployment_status": "deployed",
            "is_active": True
        })

    @staticmethod
    async def update(deployment: ModelDeployment) -> ModelDeployment:
        """Update a deployment"""
        await backend.initialize()
        deployment.update_timestamp()
        return await backend.update(deployment)

    @staticmethod
    async def delete(deployment_id: str) -> bool:
        """Soft delete a deployment (mark as inactive)"""
        await backend.initialize()
        try:
            deployment = await backend.get(deployment_id)
            if deployment:
                deployment.is_active = False
                deployment.update_timestamp()
                await backend.update(deployment)
                return True
        except:
            pass
        return False

    @staticmethod
    async def get_by_camera_ids(camera_ids: List[str]) -> List[ModelDeployment]:
        """Get deployments that contain any of the specified camera IDs"""
        await backend.initialize()
        return await backend.find({
            "camera_ids": {"$in": camera_ids},
            "is_active": True
        })

    @staticmethod
    async def get_deployment_statistics(organization_id: str) -> dict:
        """Get deployment statistics for an organization"""
        await backend.initialize()
        deployments = await backend.find({
            "organization_id": organization_id,
            "is_active": True
        })
        
        stats = {
            "total_deployments": len(deployments),
            "deployed": len([d for d in deployments if d.deployment_status == "deployed"]),
            "pending": len([d for d in deployments if d.deployment_status == "pending"]),
            "failed": len([d for d in deployments if d.deployment_status == "failed"]),
            "total_cameras": sum(len(d.camera_ids) for d in deployments)
        }
        
        return stats

    @staticmethod
    async def get_healthy_deployments(organization_id: str) -> List[ModelDeployment]:
        """Get all healthy deployments for an organization"""
        await backend.initialize()
        return await backend.find({
            "organization_id": organization_id,
            "deployment_status": "deployed",
            "health_status": "healthy",
            "is_active": True
        })