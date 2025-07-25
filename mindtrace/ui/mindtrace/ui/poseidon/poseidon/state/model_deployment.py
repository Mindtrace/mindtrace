import reflex as rx
import httpx
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from poseidon.backend.database.repositories.camera_repository import CameraRepository
from poseidon.backend.database.repositories.model_repository import ModelRepository
from poseidon.backend.database.repositories.model_deployment_repository import ModelDeploymentRepository
from poseidon.backend.database.repositories.project_repository import ProjectRepository
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
    
    # Project selection
    available_projects: List[Dict[str, str]] = []
    selected_project_id: Optional[str] = None
    selected_project_name: str = ""
    
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
    
    # User role tracking
    _is_super_admin: bool = False
    
    # Stepper state
    current_step: int = 1
    total_steps: int = 3
    
    # Model server configuration
    model_server_url: str = "http://localhost:8004"
    
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
            self.selected_project_id is not None and
            not self.is_deploying
        )
    
    @rx.var
    def project_options(self) -> List[str]:
        """Get project options for dropdown"""
        return [project["name"] for project in self.available_projects]
    
    @rx.var
    def project_names(self) -> List[str]:
        """Get project names for dropdown (matches CameraState interface)"""
        return [project["name"] for project in self.available_projects]
    
    @rx.var
    def is_super_admin(self) -> bool:
        """Check if user is super admin"""
        return self._is_super_admin
    
    @rx.var
    def has_project_selected(self) -> bool:
        """Check if a project is selected"""
        return self.selected_project_id is not None
    
    @rx.var
    def selected_project_info(self) -> str:
        """Get selected project display info"""
        if not self.selected_project_name:
            return "No project selected"
        return f"Project: {self.selected_project_name}"
    
    @rx.var
    def deployment_debug_info(self) -> str:
        """Debug info for deployment state"""
        return f"is_deploying: {self.is_deploying}, status: {self.deployment_status}"
    

    
    @rx.var
    def step_1_completed(self) -> bool:
        """Check if step 1 (project and camera selection) is completed"""
        return (
            len(self.selected_camera_ids) > 0 and
            self.selected_project_id is not None
        )
    
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
            print("Available cameras: ", self.available_cameras)
            # Add sample cameras for testing if none exist
            if len(self.available_cameras) == 0:
                from bson import ObjectId
                self.available_cameras = [
                    CameraDict(
                        id=str(ObjectId()),
                        name="weld_cam_1",
                        backend="opencv",
                        device_name="cam_001",
                        status="active",
                        configuration={"resolution": "1920x1080", "fps": 30},
                        description="-",
                        location="top"
                    ),
                    CameraDict(
                        id=str(ObjectId()),
                        name="weld_cam_2",
                        backend="rtsp",
                        device_name="cam_002",
                        status="active",
                        configuration={"resolution": "1280x720", "fps": 24},
                        description="-",
                        location="top"
                    ),
                    CameraDict(
                        id=str(ObjectId()),
                        name="weld_cam_3",
                        backend="usb",
                        device_name="cam_003",
                        status="inactive",
                        configuration={"resolution": "640x480", "fps": 15},
                        description="-",
                        location="top"
                    ),
                    CameraDict(
                        id=str(ObjectId()),
                        name="cam4",
                        backend="rtsp",
                        device_name="cam_004",
                        status="active",
                        configuration={"resolution": "1920x1080", "fps": 30},
                        description="-",
                        location="top"
                    ),
                    CameraDict(
                        id=str(ObjectId()),
                        name="cam5",
                        backend="opencv",
                        device_name="cam_005",
                        status="active",
                        configuration={"resolution": "1280x720", "fps": 24},
                        description="-",
                        location="top"
                    ),
                    CameraDict(
                        id=str(ObjectId()),
                        name="cam6",
                        backend="usb",
                        device_name="cam_006",
                        status="active",
                        configuration={"resolution": "640x480", "fps": 15},
                        description="-",
                        location="top"
                    ),
                    CameraDict(
                        id=str(ObjectId()),
                        name="cam7",
                        backend="usb",
                        device_name="cam_007",
                        status="active",
                        configuration={"resolution": "640x480", "fps": 15},
                        description="-",
                        location="top"
                    ),
                    CameraDict(
                        id=str(ObjectId()),
                        name="cam8",
                        backend="rtsp",
                        device_name="cam_008",
                        status="inactive",
                        configuration={"resolution": "1280x720", "fps": 24},
                        description="-",
                        location="top"
                    ),
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
                from bson import ObjectId
                self.available_models = [
                    ModelDict(
                        id=str(ObjectId()),
                        name="Mig66",
                        description="Weld detection model",
                        version="2.1.0",
                        type="detection",
                        framework="ONNX",
                        validation_status="validated"
                    ),
                    ModelDict(
                        id=str(ObjectId()),
                        name="Mig66 SFZ",
                        description="Spatter FZ model",
                        version="2.1.0",
                        type="detection",
                        framework="ONNX",
                        validation_status="validated"
                    ),
                    ModelDict(
                        id=str(ObjectId()),
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
                    id=str(deployment.id),
                    model_id=str(deployment.model.id) if deployment.model else "",
                    camera_ids=deployment.camera_ids,
                    deployment_status=deployment.deployment_status,
                    health_status=deployment.health_status or "unknown",
                    created_at=deployment.created_at
                )
                for deployment in deployments
            ]
            
        except Exception as e:
            self.error = f"Error loading deployments: {str(e)}"
    
    async def load_projects(self):
        """Load available projects for deployment"""
        self.is_loading = True
        self.clear_messages()
        
        try:
            # Get current user organization and role
            auth_state = await self.get_state(AuthState)
            if not auth_state.is_authenticated:
                self.error = "User not authenticated"
                return
            
            organization_id = auth_state.user_organization_id
            
            # Update super admin status
            self._is_super_admin = auth_state.is_super_admin
            
            if auth_state.is_super_admin:
                # Super admin can see all projects across all organizations
                projects = await ProjectRepository.get_all()
                # Format projects with organization names for super admins
                formatted_projects = []
                for project in projects:
                    # Extract organization info from Link field
                    if hasattr(project, 'organization') and project.organization:
                        org_name = project.organization.name if hasattr(project.organization, 'name') else "Unknown"
                        formatted_projects.append({
                            "id": str(project.id),
                            "name": f"{project.name} ({org_name})",
                            "organization_id": str(project.organization.id)
                        })
                self.available_projects = formatted_projects
            elif auth_state.is_admin:
                # Admins can see all projects in their organization
                projects = await ProjectRepository.get_by_organization(organization_id)
                self.available_projects = [
                    {
                        "id": str(project.id),
                        "name": project.name,
                        "organization_id": organization_id
                    }
                    for project in projects
                ]
            else:
                # Regular users can only see projects they're assigned to
                user_project_ids = [
                    assignment.get("project_id") 
                    for assignment in auth_state.user_project_assignments
                ]
                projects = []
                for project_id in user_project_ids:
                    project = await ProjectRepository.get_by_id(project_id)
                    if project and hasattr(project, 'organization') and project.organization:
                        # Check if project belongs to user's organization
                        if str(project.organization.id) == organization_id:
                            projects.append(project)
                
                self.available_projects = [
                    {
                        "id": str(project.id),
                        "name": project.name,
                        "organization_id": organization_id
                    }
                    for project in projects
                ]
            
            # Auto-select first project if available and no project selected
            if self.available_projects and not self.selected_project_id:
                first_project = self.available_projects[0]
                self.selected_project_id = first_project["id"]
                self.selected_project_name = first_project["name"]
            
            self.success = f"Loaded {len(self.available_projects)} projects"
            
        except Exception as e:
            self.error = f"Error loading projects: {str(e)}"
        finally:
            self.is_loading = False
    
    async def select_project(self, project_name: str):
        """Select a project for deployment"""
        for project in self.available_projects:
            if project["name"] == project_name:
                self.selected_project_id = project["id"]
                self.selected_project_name = project_name
                break
        self.clear_messages()
    
    async def select_project_by_name(self, project_name: str):
        """Select a project by name (matches CameraState interface)"""
        await self.select_project(project_name)
    
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
        # Force state update to trigger UI re-render
        yield
        self.deployment_status = "Initializing deployment..."
        self.clear_messages()
        
        try:
            # Get current user for deployment record
            auth_state = await self.get_state(AuthState)
            if not auth_state.is_authenticated:
                self.error = "User not authenticated"
                raise Exception("User not authenticated")
            
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
                raise Exception("Selected model not found")
            
# <<<<<<< poseidon/feature/state-optimization-and-critical-fixes
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
# =======
            # Step 2: Prepare camera endpoints for deployment
            self.deployment_status = "Preparing camera configurations..."
# >>>>>>> poseidon/feature/temp_demo_test
            
            # Map selected cameras to API format with endpoints
            camera_api_data = []
            for camera_id in self.selected_camera_ids:
                # Find the camera object
                camera_obj = None
                for camera in self.available_cameras:
                    if camera.id == camera_id:
                        camera_obj = camera
                        break
                
                if camera_obj:
                    # Generate camera endpoint (using default port 8082 as shown in API doc)
                    camera_endpoint = f"http://localhost:8082"
                    
                    camera_api_data.append({
                        "camera_id": camera_obj.name,  # Use camera name as camera_id for API
                        "endpoint": camera_endpoint,
                        "description": camera_obj.description or f"{camera_obj.name} - {camera_obj.backend} camera"
                    })
            
            # Step 3: Call model server API to launch model with cameras
            self.deployment_status = "Launching model with cameras..."
            
            deployment_response = None
            async with httpx.AsyncClient() as client:
                try:
                    launch_payload = {
                        "model_id": "adient_model_server",
                        "docker_image": "adient-model-server:latest",
                        "cameras": camera_api_data,
                        "gpu": True,
                        "memory_limit": "6g",
                        "environment": {
                            "MODEL_NAME": "adient_weld_detector",
                            "CONFIDENCE_THRESHOLD": "0.5"
                        }
                    }
                    
                    print(f"Sending launch request to {self.model_server_url}/models/launch")
                    print(f"Payload: {launch_payload}")
                    
                    response = await client.post(
                        f"{self.model_server_url}/models/launch",
                        json=launch_payload,
                        timeout=60.0
                    )
                    
                    if response.status_code != 200:
                        self.error = f"Model server error: {response.status_code} - {response.text}"
                        # Still try to use mock response for development
                        deployment_response = {
                            "deployment_id": "adient_model_server_mock_123",
                            "status": "running",
                            "endpoint": "http://localhost:9000",
                            "container_id": "mock_container_123",
                            "camera_ids": [cam["camera_id"] for cam in camera_api_data]
                        }
                    else:
                        deployment_response = response.json()
                        print(f"Parsed response: {deployment_response}")
                        
                        # Check if deployment failed on the server side
                        if deployment_response.get("status") == "failed":
                            print("API returned failed status, using mock response for development")
                            self.error = f"Model server deployment failed - using mock deployment for development"
                            deployment_response = {
                                "deployment_id": "adient_model_server_mock_123",
                                "status": "running",
                                "endpoint": "http://localhost:9000",
                                "container_id": "mock_container_123",
                                "camera_ids": [cam["camera_id"] for cam in camera_api_data]
                            }
                        elif not deployment_response.get("deployment_id"):
                            self.error = f"Model launch failed: Missing deployment_id in response"
                            raise Exception("Model launch failed: Missing deployment_id in response")
                        
                except httpx.TimeoutException:
                    self.error = "Model server timeout - using mock deployment"
                    # Create mock response for development
                    deployment_response = {
                        "deployment_id": "adient_model_server_mock_123",
                        "status": "running",
                        "endpoint": "http://localhost:9000",
                        "container_id": "mock_container_123",
                        "camera_ids": [cam["camera_id"] for cam in camera_api_data]
                    }
                except Exception as e:
                    self.error = f"Model server communication error: {str(e)} - using mock deployment"
# <<<<<<< poseidon/feature/state-optimization-and-critical-fixes
#                     # Continue with mock deployment for development
            
#             # Step 4: Register cameras with model server
#             self.deployment_status = "Registering cameras with model server..."
            
#             camera_names = [camera.name for camera in selected_cameras]
            
#             async with httpx.AsyncClient() as client:
#                 try:
#                     response = await client.post(
#                         f"{self.model_server_url}/model/register_cameras",
#                         json={
#                             "camera_names": camera_names,
#                             "camera_ids": self.selected_camera_ids
#                         },
#                         timeout=30.0
#                     )
                    
#                     if response.status_code != 200:
#                         self.error = f"Camera registration error: {response.status_code}"
#                         return
                        
#                 except Exception as e:
#                     # Continue with mock deployment for development
#                     pass
            
#             # Step 5: Save deployment to database
#             self.deployment_status = "Saving deployment..."
# =======
                    # Create mock response for development
                    deployment_response = {
                        "deployment_id": "adient_model_server_mock_123",
                        "status": "running", 
                        "endpoint": "http://localhost:9000",
                        "container_id": "mock_container_123",
                        "camera_ids": [cam["camera_id"] for cam in camera_api_data]
                    }
            
            # Ensure we have a valid deployment response
            if not deployment_response:
                self.error = "Failed to get deployment response from model server"
                raise Exception("Failed to get deployment response from model server")
            
            # Step 4: Save deployment to database with new schema
            self.deployment_status = "Saving deployment to database..."
# >>>>>>> poseidon/feature/temp_demo_test
            
            # Use the selected project ID from UI
            project_id = self.selected_project_id

            deployment_data = {
                "model_id": self.selected_model_id,
                "organization_id": organization_id,
                "project_id": project_id,
                "created_by_id": user_id,
                "camera_ids": self.selected_camera_ids.copy(),
                "deployment_status": "deployed",
                "model_server_url": deployment_response.get("endpoint", self.model_server_url),
                "deployment_config": {
                    "deployment_id": deployment_response.get("deployment_id"),
                    "container_id": deployment_response.get("container_id"),
                    "status": deployment_response.get("status"),
                    "model_name": selected_model.name,
                    "model_version": selected_model.version,
# <<<<<<< poseidon/feature/state-optimization-and-critical-fixes
#                     "camera_names": camera_names,
#                     "deployed_at": "2024-01-01T00:00:00Z"  # This will be set by the model
# =======
                    "docker_image": "adient-model-server:latest",
                    "cameras": camera_api_data,
                    "gpu": True,
                    "memory_limit": "6g",
                    "environment": {
                        "MODEL_NAME": "adient_weld_detector",
                        "CONFIDENCE_THRESHOLD": "0.5"
                    }
# >>>>>>> poseidon/feature/temp_demo_test
                },
                "inference_config": {
                    "endpoint": deployment_response.get("endpoint", "http://localhost:9000"),
                    "confidence_threshold": "0.5"
                },
                "resource_limits": {
                    "memory": "6g",
                    "gpu": True
                },
                "health_check_url": f"{deployment_response.get('endpoint', 'http://localhost:9000')}/health",
                "is_active": True
            }
            
            
# <<<<<<< poseidon/feature/state-optimization-and-critical-fixes
#             # Step 6: Update deployment status
#             self.deployment_status = "Deployment completed successfully!"
#             self.success = f"Successfully deployed {selected_model.name} to {len(selected_cameras)} cameras: {', '.join(camera_names)}"
# =======
            try:
                deployment = await ModelDeploymentRepository.create(deployment_data)
                if deployment:
                    print(f"DEBUG: Deployment created with ID: {deployment.id}")
                else:
                    print("DEBUG: Warning - deployment is None but no exception was raised")
                
            except Exception as db_error:
                print(f"DEBUG: ModelDeploymentRepository.create() failed: {str(db_error)}")
                print(f"DEBUG: Error type: {type(db_error)}")
                import traceback
                print(f"DEBUG: Traceback: {traceback.format_exc()}")
                raise db_error
            
            # Step 5: Update deployment status and complete
            deployment_id = deployment_response.get("deployment_id", "unknown")
            self.deployment_status = f"Deployment completed successfully! Deployment ID: {deployment_id}"
            self.success = f"Successfully deployed {selected_model.name} to {len(self.selected_camera_ids)} cameras. " \
                          f"Model endpoint: {deployment_response.get('endpoint', 'http://localhost:9000')}"
# >>>>>>> poseidon/feature/temp_demo_test
            
            # Clear selections
            self.selected_camera_ids = []
            self.selected_model_id = None
            # Keep project selection for potential next deployment
            
            # Reload deployments to show the new deployment
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
        self.selected_project_id = None
        self.selected_project_name = ""
    
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
        await self.load_projects()
        await self.load_cameras()
        await self.load_models()
        await self.load_deployments()