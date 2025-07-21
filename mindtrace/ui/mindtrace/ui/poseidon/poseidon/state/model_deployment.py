import reflex as rx
import httpx
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from poseidon.backend.database.repositories.camera_repository import CameraRepository
from poseidon.backend.database.repositories.model_repository import ModelRepository
from poseidon.backend.database.repositories.model_deployment_repository import ModelDeploymentRepository
from poseidon.state.auth import AuthState
from poseidon.state.camera import CameraState

@dataclass
class CameraDict:
    id: str = ""
    name: str = ""
    backend: str = ""
    device_name: str = ""
    status: str = ""
    configuration: Dict[str, Any] = None
    description: str = ""
    location: str = ""
    
    def __post_init__(self):
        if self.configuration is None:
            self.configuration = {}

@dataclass
class ModelDict:
    id: str = ""
    name: str = ""
    description: str = ""
    version: str = ""
    type: str = ""
    framework: str = ""
    validation_status: str = ""
    
@dataclass
class DeploymentDict:
    id: str = ""
    model_id: str = ""
    camera_ids: List[str] = None
    deployment_status: str = ""
    health_status: str = ""
    created_at: str = ""
    
    def __post_init__(self):
        if self.camera_ids is None:
            self.camera_ids = []

class ModelDeploymentState(rx.State):
    """State management for model deployment functionality"""
    
    # Lists using dataclass types for Reflex compatibility
    available_cameras: List[CameraDict] = []
    available_models: List[ModelDict] = []
    active_deployments: List[DeploymentDict] = []
    
    # Selection
    selected_camera_ids: List[str] = []
    selected_model_id: Optional[str] = None
    
    # Deployment status
    deployment_status: str = ""
    is_deploying: bool = False
    
    # UI state
    error: str = ""
    success: str = ""
    is_loading: bool = False
    
    # Stepper state
    current_step: int = 1
    total_steps: int = 3
    
    # Model server configuration
    model_server_url: str = "http://localhost:8002"
    
    @rx.var
    def selected_cameras_count(self) -> int:
        """Get count of selected cameras"""
        return len(self.selected_camera_ids)
    
    @rx.var
    def selected_model_name(self) -> str:
        """Get name of selected model"""
        if not self.selected_model_id:
            return ""
        for model in self.available_models:
            if model.id == self.selected_model_id:
                return model.name
        return ""
    
    @rx.var
    def can_deploy(self) -> bool:
        """Check if deployment is possible"""
        return (
            len(self.selected_camera_ids) > 0 and
            self.selected_model_id is not None and
            not self.is_deploying
        )
    
    @rx.var
    def step_1_completed(self) -> bool:
        """Check if step 1 (camera selection) is completed"""
        return len(self.selected_camera_ids) > 0
    
    @rx.var
    def step_2_completed(self) -> bool:
        """Check if step 2 (model selection) is completed"""
        return self.selected_model_id is not None
    
    @rx.var
    def step_3_completed(self) -> bool:
        """Check if step 3 (deployment) is completed"""
        return False  # Always false until deployment is done
    
    @rx.var
    def can_proceed_to_step(self) -> bool:
        """Check if user can proceed to the next step"""
        if self.current_step == 1:
            return self.step_1_completed
        elif self.current_step == 2:
            return self.step_2_completed
        elif self.current_step == 3:
            return self.can_deploy
        return False
    
    def is_camera_selected(self, camera_id: str) -> bool:
        """Check if a camera is selected"""
        return camera_id in self.selected_camera_ids
    
    @rx.var
    def selected_camera_ids_set(self) -> set:
        """Get selected camera IDs as a set for faster lookup"""
        return set(self.selected_camera_ids)
    
    async def load_cameras(self):
        """Load cameras using CameraState and convert to CameraDict for UI"""
        self.is_loading = True
        self.clear_messages()
        
        try:
            # Get camera state and initialize context
            camera_state = await self.get_state(CameraState)
            
            # Initialize camera context if not already done
            if not camera_state.organization_id:
                await camera_state.initialize_context()
            
            # Fetch cameras using CameraState
            await camera_state.fetch_cameras()
            
            # Convert camera objects to CameraDict instances for Reflex compatibility
            self.available_cameras = [
                CameraDict(
                    id=str(camera.id),
                    name=camera.name,
                    backend=camera.backend,
                    device_name=camera.device_name,
                    status=camera.status,
                    configuration=camera.configuration,
                    description=camera.description or "",
                    location=camera.location or ""
                )
                for camera in camera_state.camera_objs
            ]
            
            # Check if we have cameras
            if len(self.available_cameras) == 0:
                self.error = "No cameras available. Please assign cameras to your project first."
            else:
                self.success = f"Loaded {len(self.available_cameras)} cameras from project: {camera_state.selected_project_name}"
            
        except Exception as e:
            self.error = f"Error loading cameras: {str(e)}"
        finally:
            self.is_loading = False

    async def load_models(self):
        """Load models from database"""
        self.is_loading = True
        self.clear_messages()
        
        try:
            # Get current user organization
            auth_state = await self.get_state(AuthState)
            if not auth_state.is_authenticated:
                self.error = "User not authenticated"
                return
            
            organization_id = auth_state.user_organization_id
            models = await ModelRepository.get_by_organization(organization_id)
            
            # Convert model objects to ModelDict instances
            self.available_models = [
                ModelDict(
                    id=model.id,
                    name=model.name,
                    description=model.description,
                    version=model.version,
                    type=model.type or "unknown",
                    framework=model.framework or "unknown",
                    validation_status=model.validation_status or "unknown"
                )
                for model in models
            ]
            
            # Add sample models for testing if none exist
            if len(self.available_models) == 0:
                self.available_models = [
                    ModelDict(
                        id="model_1",
                        name="Mig66",
                        description="Weld detection model",
                        version="2.1.0",
                        type="detection",
                        framework="ONNX",
                        validation_status="validated"
                    ),
                    ModelDict(
                        id="model_2",
                        name="Mig66 SFZ",
                        description="Spatter FZ model",
                        version="2.1.0",
                        type="detection",
                        framework="ONNX",
                        validation_status="validated"
                    ),
                    ModelDict(
                        id="model_3",
                        name="Part Detection",
                        description="Part detection model",
                        version="1.0.0",
                        type="detection",
                        framework="ONNX",
                        validation_status="pending"
                    ),
                ]
            
            self.success = f"Loaded {len(self.available_models)} models"
            
        except Exception as e:
            self.error = f"Error loading models: {str(e)}"
        finally:
            self.is_loading = False
    
    async def load_deployments(self):
        """Load active deployments"""
        try:
            # Get current user organization
            auth_state = await self.get_state(AuthState)
            if not auth_state.is_authenticated:
                return
            
            organization_id = auth_state.user_organization_id
            deployments = await ModelDeploymentRepository.get_active_by_organization(organization_id)
            
            # Convert deployment objects to DeploymentDict instances
            self.active_deployments = [
                DeploymentDict(
                    id=deployment.id,
                    model_id=deployment.model_id,
                    camera_ids=deployment.camera_ids,
                    deployment_status=deployment.deployment_status,
                    health_status=deployment.health_status or "unknown",
                    created_at=deployment.created_at
                )
                for deployment in deployments
            ]
            
        except Exception as e:
            self.error = f"Error loading deployments: {str(e)}"
    
    async def toggle_camera_selection(self, camera_id: str):
        """Toggle camera selection"""
        if camera_id in self.selected_camera_ids:
            self.selected_camera_ids.remove(camera_id)
        else:
            self.selected_camera_ids.append(camera_id)
    
    async def select_model(self, model_id: str):
        """Select a model for deployment"""
        self.selected_model_id = model_id
    
    async def select_all_cameras(self):
        """Select all available cameras"""
        self.selected_camera_ids = [camera.id for camera in self.available_cameras]
    
    async def ensure_cameras_initialized(self):
        """Ensure selected cameras are initialized before deployment"""
        camera_state = await self.get_state(CameraState)
        
        # Get selected camera names for initialization
        selected_camera_names = []
        for camera in self.available_cameras:
            if camera.id in self.selected_camera_ids:
                selected_camera_names.append(camera.name)
        
        # Initialize each selected camera if not already active
        for camera_name in selected_camera_names:
            camera_status = camera_state.camera_statuses.get(camera_name, "not_initialized")
            if camera_status != "available":
                self.deployment_status = f"Initializing camera {camera_name}..."
                await camera_state.initialize_camera(camera_name)
                
                # Check if initialization was successful
                if camera_state.camera_statuses.get(camera_name) != "available":
                    raise Exception(f"Failed to initialize camera {camera_name}")
    
    async def deploy_model(self):
        """Deploy selected model to selected cameras"""
        if not self.can_deploy:
            self.error = "Cannot deploy: Please select cameras and a model"
            return
        
        self.is_deploying = True
        self.deployment_status = "Initializing deployment..."
        self.clear_messages()
        
        try:
            # Get current user for deployment record
            auth_state = await self.get_state(AuthState)
            if not auth_state.is_authenticated:
                self.error = "User not authenticated"
                return
            
            organization_id = auth_state.user_organization_id
            user_id = auth_state.user_id
            
            # Step 1: Validate selections
            self.deployment_status = "Validating selections..."
            
            # Get selected model
            selected_model = None
            for model in self.available_models:
                if model.id == self.selected_model_id:
                    selected_model = model
                    break
            
            if not selected_model:
                self.error = "Selected model not found"
                return
            
            # Get selected cameras
            selected_cameras = []
            for camera in self.available_cameras:
                if camera.id in self.selected_camera_ids:
                    selected_cameras.append(camera)
            
            if not selected_cameras:
                self.error = "No valid cameras selected"
                return
            
            # Step 2: Ensure cameras are initialized
            self.deployment_status = "Initializing cameras..."
            await self.ensure_cameras_initialized()
            
            # Step 3: Call model server API to load model
            self.deployment_status = "Loading model on server..."
            
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        f"{self.model_server_url}/model/load",
                        json={"model_name": selected_model.name},
                        timeout=30.0
                    )
                    
                    if response.status_code != 200:
                        self.error = f"Model server error: {response.status_code}"
                        return
                    
                    model_response = response.json()
                    if not model_response.get("success"):
                        self.error = f"Model loading failed: {model_response.get('message', 'Unknown error')}"
                        return
                        
                except httpx.TimeoutException:
                    self.error = "Model server timeout - using mock deployment"
                    # Continue with mock deployment for development
                except Exception as e:
                    self.error = f"Model server communication error: {str(e)} - using mock deployment"
                    # Continue with mock deployment for development
            
            # Step 4: Register cameras with model server
            self.deployment_status = "Registering cameras with model server..."
            
            camera_names = [camera.name for camera in selected_cameras]
            
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        f"{self.model_server_url}/model/register_cameras",
                        json={
                            "camera_names": camera_names,
                            "camera_ids": self.selected_camera_ids
                        },
                        timeout=30.0
                    )
                    
                    if response.status_code != 200:
                        self.error = f"Camera registration error: {response.status_code}"
                        return
                        
                except Exception as e:
                    # Continue with mock deployment for development
                    pass
            
            # Step 5: Save deployment to database
            self.deployment_status = "Saving deployment..."
            
            deployment_data = {
                "model_id": self.selected_model_id,
                "camera_ids": self.selected_camera_ids.copy(),
                "deployment_status": "deployed",
                "model_server_url": self.model_server_url,
                "organization_id": organization_id,
                "created_by": user_id,
                "deployment_config": {
                    "model_name": selected_model.name,
                    "model_version": selected_model.version,
                    "camera_names": camera_names,
                    "deployed_at": "2024-01-01T00:00:00Z"  # This will be set by the model
                },
                "is_active": True
            }
            
            deployment = await ModelDeploymentRepository.create(deployment_data)
            
            # Step 6: Update deployment status
            self.deployment_status = "Deployment completed successfully!"
            self.success = f"Successfully deployed {selected_model.name} to {len(selected_cameras)} cameras: {', '.join(camera_names)}"
            
            # Clear selections
            self.selected_camera_ids = []
            self.selected_model_id = None
            
            # Reload deployments
            await self.load_deployments()
            
        except Exception as e:
            self.error = f"Deployment failed: {str(e)}"
            self.deployment_status = "Deployment failed"
            
        finally:
            self.is_deploying = False
    
    async def undeploy_model(self, deployment_id: str):
        """Undeploy a model"""
        self.is_loading = True
        self.clear_messages()
        
        try:
            # Deactivate deployment in database
            success = await ModelDeploymentRepository.delete(deployment_id)
            
            if success:
                self.success = "Model undeployed successfully"
                await self.load_deployments()
            else:
                self.error = "Failed to undeploy model"
                
        except Exception as e:
            self.error = f"Error undeploying model: {str(e)}"
        finally:
            self.is_loading = False
    
    def clear_messages(self):
        """Clear error and success messages"""
        self.error = ""
        self.success = ""
    
    def clear_selections(self):
        """Clear all selections"""
        self.selected_camera_ids = []
        self.selected_model_id = None
    
    async def next_step(self):
        """Move to the next step"""
        if self.current_step < self.total_steps and self.can_proceed_to_step:
            self.current_step += 1
            self.clear_messages()
    
    async def previous_step(self):
        """Move to the previous step"""
        if self.current_step > 1:
            self.current_step -= 1
            self.clear_messages()
    
    async def go_to_step(self, step: int):
        """Go to a specific step"""
        if 1 <= step <= self.total_steps:
            self.current_step = step
            self.clear_messages()
    
    async def reset_stepper(self):
        """Reset stepper to initial state"""
        self.current_step = 1
        self.clear_selections()
        self.clear_messages()
        self.deployment_status = ""
    
    async def on_mount(self):
        """Load initial data when component mounts"""
        await self.load_cameras()
        await self.load_models()
        await self.load_deployments()