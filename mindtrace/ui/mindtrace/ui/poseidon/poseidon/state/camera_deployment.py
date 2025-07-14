import reflex as rx
from typing import List, Optional
from dataclasses import dataclass
import asyncio

@dataclass
class CameraDict:
    id: str = ""
    name: str = ""
    location: str = ""
    ip_address: str = ""
    status: str = "offline"  # online, offline, error
    model: str = ""
    last_seen: str = ""
    created_at: str = ""

@dataclass
class ModelDict:
    id: str = ""
    name: str = ""
    version: str = ""
    type: str = ""  # object_detection, classification, etc.
    description: str = ""
    size_mb: int = 0
    accuracy: float = 0.0
    status: str = "available"  # available, loading, error
    created_at: str = ""

@dataclass
class InferenceServerDict:
    id: str = ""
    name: str = ""
    cameras: List[str] = None
    model_id: str = ""
    status: str = "created"  # created, deploying, running, stopped, error
    endpoint: str = ""
    created_at: str = ""
    
    def __post_init__(self):
        if self.cameras is None:
            self.cameras = []

class CameraDeploymentState(rx.State):
    # Camera management
    cameras: List[CameraDict] = []
    selected_cameras: List[str] = []
    
    # Model management
    models: List[ModelDict] = []
    selected_model_id: str = ""
    selected_model: Optional[ModelDict] = None
    
    # Inference servers
    inference_servers: List[InferenceServerDict] = []
    
    # UI state
    is_loading_cameras: bool = False
    is_loading_models: bool = False
    is_deploying: bool = False
    deployment_status: str = ""
    deployment_error: str = ""
    
    # Modal states
    show_deployment_modal: bool = False
    show_server_details_modal: bool = False
    selected_server: Optional[InferenceServerDict] = None
    
    def load_mock_data(self):
        """Load mock camera and model data"""
        self.cameras = [
            CameraDict(
                id="cam_001",
                name="Front Entrance Camera",
                location="Building A - Main Entrance",
                ip_address="192.168.1.101",
                status="online",
                model="yolo_v8_detection",
                last_seen="2024-01-15 10:30:00",
                created_at="2024-01-01 09:00:00"
            ),
            CameraDict(
                id="cam_002", 
                name="Warehouse Camera 1",
                location="Warehouse - Zone A",
                ip_address="192.168.1.102",
                status="online",
                model="",
                last_seen="2024-01-15 10:29:45",
                created_at="2024-01-02 14:15:00"
            ),
            CameraDict(
                id="cam_003",
                name="Parking Lot Camera",
                location="Parking Lot - Section B",
                ip_address="192.168.1.103", 
                status="offline",
                model="vehicle_detection_v2",
                last_seen="2024-01-14 18:45:00",
                created_at="2024-01-03 11:30:00"
            ),
            CameraDict(
                id="cam_004",
                name="Factory Floor Camera 2",
                location="Factory - Production Line 2",
                ip_address="192.168.1.104",
                status="online",
                model="",
                last_seen="2024-01-15 10:31:20",
                created_at="2024-01-05 08:45:00"
            ),
        ]
        
        self.models = [
            ModelDict(
                id="yolo_v8_detection",
                name="YOLO v8 Object Detection",
                version="1.2.3",
                type="object_detection",
                description="High-performance real-time object detection model",
                size_mb=245,
                accuracy=92.5,
                status="available",
                created_at="2024-01-01 12:00:00"
            ),
            ModelDict(
                id="vehicle_detection_v2",
                name="Vehicle Detection v2",
                version="2.1.0", 
                type="vehicle_detection",
                description="Specialized model for vehicle and license plate detection",
                size_mb=180,
                accuracy=89.3,
                status="available",
                created_at="2024-01-05 14:30:00"
            ),
            ModelDict(
                id="person_classifier",
                name="Person Classification",
                version="1.0.5",
                type="classification",
                description="Advanced person detection and classification model",
                size_mb=120,
                accuracy=94.8,
                status="available",
                created_at="2024-01-10 09:15:00"
            ),
            ModelDict(
                id="anomaly_detection",
                name="Anomaly Detection",
                version="3.0.1",
                type="anomaly_detection", 
                description="Real-time anomaly detection for industrial environments",
                size_mb=320,
                accuracy=87.2,
                status="loading",
                created_at="2024-01-12 16:45:00"
            ),
        ]
        
        self.inference_servers = [
            InferenceServerDict(
                id="server_001",
                name="Main Entrance Inference",
                cameras=["cam_001"],
                model_id="yolo_v8_detection",
                status="running",
                endpoint="http://inference-1.local:8080",
                created_at="2024-01-10 14:20:00"
            ),
            InferenceServerDict(
                id="server_002",
                name="Parking Detection System",
                cameras=["cam_003"],
                model_id="vehicle_detection_v2", 
                status="stopped",
                endpoint="http://inference-2.local:8080",
                created_at="2024-01-12 11:30:00"
            ),
        ]
    
    def toggle_camera_selection(self, camera_id: str):
        """Toggle camera selection for deployment"""
        if camera_id in self.selected_cameras:
            self.selected_cameras.remove(camera_id)
        else:
            self.selected_cameras.append(camera_id)
    
    def set_selected_model(self, model_id: str):
        """Set the selected model and update model server"""
        self.selected_model_id = model_id
        self.selected_model = next((m for m in self.models if m.id == model_id), None)
        
        # Simulate API call to update model server
        asyncio.create_task(self._update_model_server(model_id))
    
    async def _update_model_server(self, model_id: str):
        """Simulate updating model server with new model"""
        # Simulate API delay
        await asyncio.sleep(1)
        print(f"Model server updated with model: {model_id}")
    
    def open_deployment_modal(self):
        """Open deployment confirmation modal"""
        if len(self.selected_cameras) > 0 and self.selected_model_id:
            self.show_deployment_modal = True
            self.deployment_error = ""
        else:
            self.deployment_error = "Please select at least one camera and a model"
    
    def close_deployment_modal(self):
        """Close deployment modal"""
        self.show_deployment_modal = False
        self.deployment_error = ""
    
    async def deploy_inference_server(self, form_data):
        """Deploy a new inference server with selected cameras and model"""
        server_name = form_data.get("server_name", "").strip()
        if not server_name:
            self.deployment_error = "Please provide a server name"
            return
            
        self.is_deploying = True
        self.deployment_status = "Creating inference server..."
        
        try:
            # Simulate deployment process
            await asyncio.sleep(2)
            self.deployment_status = "Configuring cameras..."
            await asyncio.sleep(1.5)
            self.deployment_status = "Loading model..."
            await asyncio.sleep(2)
            self.deployment_status = "Starting inference server..."
            await asyncio.sleep(1)
            
            # Create new inference server
            new_server = InferenceServerDict(
                id=f"server_{len(self.inference_servers) + 1:03d}",
                name=server_name,
                cameras=self.selected_cameras.copy(),
                model_id=self.selected_model_id,
                status="running",
                endpoint=f"http://inference-{len(self.inference_servers) + 1}.local:8080",
                created_at="2024-01-15 10:35:00"
            )
            
            self.inference_servers.append(new_server)
            
            # Clear selections
            self.selected_cameras = []
            self.selected_model_id = ""
            self.selected_model = None
            
            self.deployment_status = "Deployment successful!"
            await asyncio.sleep(1)
            
            self.close_deployment_modal()
            
        except Exception as e:
            self.deployment_error = f"Deployment failed: {str(e)}"
        finally:
            self.is_deploying = False
            self.deployment_status = ""
    
    def open_server_details(self, server: InferenceServerDict):
        """Open server details modal"""
        self.selected_server = server
        self.show_server_details_modal = True
    
    def close_server_details_modal(self):
        """Close server details modal"""
        self.show_server_details_modal = False
        self.selected_server = None
    
    async def stop_inference_server(self, server_id: str):
        """Stop an inference server"""
        server = next((s for s in self.inference_servers if s.id == server_id), None)
        if server:
            server.status = "stopped"
            await asyncio.sleep(0.5)  # Simulate API call
    
    async def start_inference_server(self, server_id: str):
        """Start an inference server"""
        server = next((s for s in self.inference_servers if s.id == server_id), None)
        if server:
            server.status = "running"
            await asyncio.sleep(0.5)  # Simulate API call
    
    async def delete_inference_server(self, server_id: str):
        """Delete an inference server"""
        self.inference_servers = [s for s in self.inference_servers if s.id != server_id]
        await asyncio.sleep(0.5)  # Simulate API call
        self.close_server_details_modal() 