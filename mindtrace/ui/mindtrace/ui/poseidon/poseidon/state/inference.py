import reflex as rx
import httpx
from typing import List, Dict, Optional, Any
from datetime import datetime
import uuid

from poseidon.backend.database.repositories.scan_repository import ScanRepository
from poseidon.backend.database.repositories.scan_image_repository import ScanImageRepository
from poseidon.backend.database.repositories.scan_classification_repository import ScanClassificationRepository
from poseidon.backend.database.repositories.model_deployment_repository import ModelDeploymentRepository
from poseidon.backend.database.models.enums import ScanStatus, ScanImageStatus, CameraStatus
from poseidon.backend.core.config import settings
from poseidon.state.auth import AuthState


class ScanHistoryItem(rx.Base):
    """Data model for scan history items"""
    serial_number: str
    timestamp: str
    formatted_timestamp: str
    status: str
    is_healthy: bool


class InferenceState(rx.State):
    """State management for inference operations."""
    
    # Form inputs
    serial_number: str = ""
    selected_deployment_id: str = ""
    
    # Model deployments for dropdown
    available_deployments: List[Dict[str, Any]] = []
    
    # Scan state
    is_scanning: bool = False
    scan_button_enabled: bool = False
    
    # Scan history since page opened - now properly typed
    scan_history: List[ScanHistoryItem] = []
    
    # Current scan results
    current_scan_results: Optional[Dict[str, Any]] = None
    
    # UI state - replicating BaseManagementState functionality
    error: str = ""
    success: str = ""
    loading: bool = False
    
    def clear_messages(self):
        """Clear success and error messages"""
        self.error = ""
        self.success = ""
    
    async def get_auth_state(self) -> AuthState:
        """Get the current auth state"""
        return await self.get_state(AuthState)
    
    # Constants
    INFERENCE_API_URL: str = "http://localhost:8004/inference/run"
    
    @rx.var
    def deployment_options(self) -> List[Dict[str, str]]:
        """Convert deployments to options format for select component"""
        return [
            {"id": dep["id"], "name": dep["deployment_id"]}
            for dep in self.available_deployments
        ]
    
    @rx.var 
    def can_scan(self) -> bool:
        """Check if scan button should be enabled"""
        return (
            self.serial_number.strip() != "" and
            self.selected_deployment_id != "" and
            not self.is_scanning
        )
    
    def set_serial_number(self, value: str):
        """Set serial number and update scan button state"""
        self.serial_number = value
        self.update_scan_button_state()
    
    def set_selected_deployment_id(self, value: str):
        """Set selected deployment ID and update scan button state"""
        self.selected_deployment_id = value
        self.update_scan_button_state()
    
    def update_scan_button_state(self):
        """Update scan button enabled state"""
        self.scan_button_enabled = self.can_scan
    
    async def load_model_deployments(self):
        """Load available model deployments for the current user/organization"""
        try:
            self.loading = True
            self.clear_messages()
            
            auth_state = await self.get_auth_state()
            if not auth_state.is_authenticated:
                self.error = "User not authenticated"
                return
            
            # Get deployments scoped to user's organization
            deployments = await ModelDeploymentRepository.get_by_organization(
                auth_state.user_organization_id
            )
            
            # Convert to format suitable for dropdown
            self.available_deployments = []
            for deployment in deployments:
                try:
                    # Try to fetch all links first
                    await deployment.fetch_all_links()
                    
                    # Extract deployment_id from deployment_config
                    deployment_id = "Unknown Deployment"
                    if hasattr(deployment, 'deployment_config') and deployment.deployment_config:
                        if isinstance(deployment.deployment_config, dict) and 'deployment_id' in deployment.deployment_config:
                            deployment_id = deployment.deployment_config['deployment_id']
                    
                    # Safely extract model name for additional context
                    model_name = "Unknown Model"
                    if hasattr(deployment, 'model') and deployment.model:
                        if hasattr(deployment.model, 'name'):
                            model_name = deployment.model.name
                        elif hasattr(deployment.model, 'id'):
                            # If we only have the Link, try to get the actual model
                            from poseidon.backend.database.models.model import Model
                            try:
                                actual_model = await Model.get(deployment.model.id)
                                if actual_model:
                                    model_name = actual_model.name
                            except:
                                pass
                    
                    # Safely extract project name for additional context
                    project_name = "Unknown Project"
                    if hasattr(deployment, 'project') and deployment.project:
                        if hasattr(deployment.project, 'name'):
                            project_name = deployment.project.name
                        elif hasattr(deployment.project, 'id'):
                            # If we only have the Link, try to get the actual project
                            from poseidon.backend.database.models.project import Project
                            try:
                                actual_project = await Project.get(deployment.project.id)
                                if actual_project:
                                    project_name = actual_project.name
                            except:
                                pass
                    
                    # Safely extract deployment status
                    deployment_status = "unknown"
                    if hasattr(deployment, 'deployment_status'):
                        if hasattr(deployment.deployment_status, 'value'):
                            deployment_status = deployment.deployment_status.value
                        else:
                            deployment_status = str(deployment.deployment_status)
                    
                    self.available_deployments.append({
                        "id": str(deployment.id),
                        "deployment_id": deployment_id,
                        "model_name": model_name,
                        "project_name": project_name,
                        "status": deployment_status,
                        "camera_count": len(deployment.camera_ids) if hasattr(deployment, 'camera_ids') and deployment.camera_ids else 0
                    })
                    
                except Exception as e:
                    # Log the specific deployment that failed and continue with others
                    print(f"Error processing deployment {deployment.id}: {str(e)}")
                    # Add a basic entry even if we can't get all details
                    self.available_deployments.append({
                        "id": str(deployment.id),
                        "deployment_id": "Error Loading Deployment ID",
                        "model_name": "Error Loading Model",
                        "project_name": "Error Loading Project", 
                        "status": "unknown",
                        "camera_count": 0
                    })
            
        except Exception as e:
            self.error = f"Failed to load model deployments: {str(e)}"
        finally:
            self.loading = False
    
    def get_mock_response(self) -> Dict[str, Any]:
        """Generate mock response for development"""
        return {
            "inference_id": str(uuid.uuid4()),
            "deployment_id": self.selected_deployment_id,
            "status": "success",
            "cls_result": "Defective",
            "results": {
                "weld_cam_1": {
                    "camera_id": "weld_cam_1",
                    "status": "success",
                    "gcs_path": "images/weld_cam_1/scan_001.jpg",
                    "detections": [
                        {
                            "class": "Healthy",
                            "confidence": 0.95,
                            "bbox": [100, 200, 300, 400]
                        }
                    ],
                    "error": None,
                    "processing_time": 1.23
                },
                "weld_cam_2": {
                    "camera_id": "weld_cam_2",
                    "status": "success", 
                    "gcs_path": "images/weld_cam_2/scan_002.jpg",
                    "detections": [
                        {
                            "class": "Porosity",
                            "confidence": 0.87,
                            "bbox": [150, 250, 350, 450]
                        }
                    ],
                    "error": None,
                    "processing_time": 1.45
                },
                "weld_cam_3": {
                    "camera_id": "weld_cam_3",
                    "status": "success",
                    "gcs_path": "images/weld_cam_3/scan_003.jpg", 
                    "detections": [],
                    "error": None,
                    "processing_time": 1.12
                }
            },
            "total_time": 3.8
        }
    
    async def run_inference(self):
        """Run inference on the selected deployment"""
        if not self.can_scan:
            self.error = "Cannot scan: Please enter serial number and select deployment"
            return
        
        self.is_scanning = True
        self.clear_messages()
        
        try:
            auth_state = await self.get_auth_state()
            if not auth_state.is_authenticated:
                self.error = "User not authenticated"
                return
            
            # Prepare request payload
            payload = {
                "deployment_id": self.selected_deployment_id,
                "timeout": 30.0
            }
            
            # TODO: Uncomment this when inference API is ready
            # async with httpx.AsyncClient() as client:
            #     response = await client.post(
            #         self.INFERENCE_API_URL,
            #         json=payload,
            #         timeout=35.0
            #     )
            #     
            #     if response.status_code == 200:
            #         response_data = response.json() 
            #     else:
            #         raise Exception(f"API returned {response.status_code}: {response.text}")
            
            # MOCK: Use mock response for development
            response_data = self.get_mock_response()
            
            # Store current scan results for display
            self.current_scan_results = response_data
            
            # Create database records
            await self.create_scan_records(response_data, auth_state)
            
            # Add to scan history
            timestamp = datetime.now().isoformat()
            scan_summary = ScanHistoryItem(
                serial_number=self.serial_number,
                timestamp=timestamp,
                formatted_timestamp=timestamp[:19].replace("T", " ") if len(timestamp) >= 19 else timestamp,
                status=response_data.get("cls_result", "Unknown"),
                is_healthy=response_data.get("cls_result") == "Healthy"
            )
            self.scan_history.append(scan_summary)
            
            self.success = f"Scan completed successfully. Result: {response_data.get('cls_result', 'Unknown')}"
            
        except Exception as e:
            self.error = f"Scan failed: {str(e)}"
        finally:
            self.is_scanning = False
    
    async def create_scan_records(self, response_data: Dict[str, Any], auth_state):
        """Create scan, scan_image, and scan_classification records in database"""
        try:
            # Find the selected deployment
            deployment = await ModelDeploymentRepository.get_by_id(self.selected_deployment_id)
            if not deployment:
                raise Exception("Deployment not found")
            
            # Fetch deployment links to ensure we have the actual objects
            await deployment.fetch_all_links()
            
            # Create scan record
            scan_data = {
                "serial_number": self.serial_number,
                "organization": deployment.organization,
                "project": deployment.project,
                "model_deployment": deployment,
                "status": ScanStatus.COMPLETED,
                "cls_result": response_data.get("cls_result"),
                "cls_confidence": self._calculate_overall_confidence(response_data),
                "cls_pred_time": response_data.get("total_time")
            }
            
            # Add user if available
            if auth_state.user_id:
                from poseidon.backend.database.models.user import User
                try:
                    user = await User.get(auth_state.user_id)
                    if user:
                        scan_data["user"] = user
                except:
                    pass  # Continue without user if not found
            
            scan = await ScanRepository.create(scan_data)
            
            # Create scan_image records for each camera
            results = response_data.get("results", {})
            for camera_id, camera_result in results.items():
                if camera_result.get("status") == "success":
                    try:
                        # Try to find camera by camera_id in the deployment's camera_ids
                        camera = None
                        if hasattr(deployment, 'camera_ids') and deployment.camera_ids:
                            # Look for a camera with this camera_id in the deployment
                            from poseidon.backend.database.repositories.camera_repository import CameraRepository
                            # Try to get camera by ID first
                            for cam_id in deployment.camera_ids:
                                try:
                                    potential_camera = await CameraRepository.get_by_id(cam_id)
                                    if potential_camera and hasattr(potential_camera, 'name') and potential_camera.name == camera_id:
                                        camera = potential_camera
                                        break
                                except:
                                    continue
                            
                            # If not found by name match, just use the first available camera for now
                            if not camera and deployment.camera_ids:
                                try:
                                    camera = await CameraRepository.get_by_id(deployment.camera_ids[0])
                                except:
                                    pass
                        
                        # If we still don't have a camera, create one
                        if not camera:
                            print(f"Camera {camera_id} not found, creating new camera...")
                            from poseidon.backend.database.repositories.camera_repository import CameraRepository
                            try:
                                # Create new camera with basic info
                                camera_data = {
                                    "name": camera_id,
                                    "organization": deployment.organization,
                                    "project": deployment.project,
                                    "backend": "auto_created",
                                    "device_name": camera_id,
                                    "status": CameraStatus.ACTIVE,
                                    "description": f"Auto-created camera for inference scan {self.serial_number}",
                                    "location": "Unknown",
                                    "configuration": {
                                        "auto_created": True,
                                        "created_for_scan": self.serial_number
                                    }
                                }
                                
                                # Add user if available
                                if auth_state.user_id:
                                    try:
                                        from poseidon.backend.database.models.user import User
                                        user = await User.get(auth_state.user_id)
                                        if user:
                                            camera_data["created_by"] = user
                                        else:
                                            print(f"User {auth_state.user_id} not found, cannot create camera")
                                            continue
                                    except Exception as user_error:
                                        print(f"Failed to get user {auth_state.user_id}: {str(user_error)}, cannot create camera")
                                        continue
                                else:
                                    print("No authenticated user available, cannot create camera")
                                    continue
                                
                                camera = await CameraRepository.create_or_update(camera_data)
                                print(f"Successfully created camera {camera_id} with ID: {camera.id}")
                                
                                # Add the new camera to the deployment's camera_ids for future use
                                if hasattr(deployment, 'camera_ids') and isinstance(deployment.camera_ids, list):
                                    if str(camera.id) not in deployment.camera_ids:
                                        deployment.camera_ids.append(str(camera.id))
                                        await deployment.save()
                                        print(f"Added camera {camera.id} to deployment {deployment.id}")
                                
                            except Exception as create_error:
                                print(f"Failed to create camera {camera_id}: {str(create_error)}")
                                # Continue without camera - this will still fail but at least we tried
                                continue
                        
                        # Create scan_image record
                        gcs_path = camera_result.get("gcs_path", "")
                        file_name = gcs_path.split("/")[-1] if gcs_path else f"{camera_id}_scan.jpg"
                        path_without_filename = "/".join(gcs_path.split("/")[:-1]) if gcs_path else f"scans/{self.serial_number}"
                        
                        scan_image_data = {
                            "organization": deployment.organization,
                            "project": deployment.project,
                            "camera": camera,
                            "scan": scan,
                            "status": ScanImageStatus.PROCESSED,
                            "file_name": file_name,
                            "path": path_without_filename,
                            "bucket_name": settings.GCP_BUCKET_NAME,
                            "full_path": f"gs://{settings.GCP_BUCKET_NAME}/{gcs_path}" if gcs_path else f"gs://{settings.GCP_BUCKET_NAME}/{path_without_filename}/{file_name}"
                        }
                        
                        # Add user if available
                        if auth_state.user_id:
                            try:
                                from poseidon.backend.database.models.user import User
                                user = await User.get(auth_state.user_id)
                                if user:
                                    scan_image_data["user"] = user
                            except:
                                pass
                        
                        scan_image = await ScanImageRepository.create(scan_image_data)
                        print(f"Created scan_image with ID: {scan_image.id}")
                        
                        # Create scan_classification records for each detection
                        detections = camera_result.get("detections", [])
                        for detection in detections:
                            classification_data = {
                                "image": scan_image,
                                "scan": scan,
                                "name": detection.get("class", "Unknown"),
                                "cls_confidence": detection.get("confidence"),
                                "cls_pred_time": camera_result.get("processing_time"),
                                "det_cls": detection.get("class"),
                            }
                            
                            # Add bounding box if available
                            bbox = detection.get("bbox")
                            if bbox and len(bbox) == 4:
                                classification_data.update({
                                    "det_x": float(bbox[0]),
                                    "det_y": float(bbox[1]), 
                                    "det_w": float(bbox[2] - bbox[0]),
                                    "det_h": float(bbox[3] - bbox[1])
                                })
                            
                            classification = await ScanClassificationRepository.create(classification_data)
                            print(f"Created scan_classification with ID: {classification.id}")
                        
                        print(f"Successfully processed camera {camera_id}: created 1 scan_image and {len(detections)} classifications")
                        
                    except Exception as e:
                        print(f"Error creating scan_image/classifications for camera {camera_id}: {str(e)}")
                        continue
            
        except Exception as e:
            # Log error but don't fail the entire scan
            print(f"Error creating database records: {str(e)}")
            import traceback
            traceback.print_exc()
            # You might want to set a warning message instead of error
    
    def _calculate_overall_confidence(self, response_data: Dict[str, Any]) -> Optional[float]:
        """Calculate overall confidence from all detections"""
        all_confidences = []
        results = response_data.get("results", {})
        
        for camera_result in results.values():
            detections = camera_result.get("detections", [])
            for detection in detections:
                confidence = detection.get("confidence")
                if confidence is not None:
                    all_confidences.append(confidence)
        
        return sum(all_confidences) / len(all_confidences) if all_confidences else None
    
    def clear_form(self):
        """Clear the form inputs"""
        self.serial_number = ""
        self.selected_deployment_id = ""
        self.update_scan_button_state()
        self.clear_messages()
    
    def clear_scan_history(self):
        """Clear the scan history"""
        self.scan_history = []
    
    async def on_mount(self):
        """Initialize the page when mounted"""
        await self.load_model_deployments() 