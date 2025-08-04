import reflex as rx
import httpx
from typing import List, Dict, Optional, Any
from datetime import datetime

from poseidon.backend.database.repositories.scan_repository import ScanRepository
from poseidon.backend.database.repositories.scan_image_repository import ScanImageRepository
from poseidon.backend.database.repositories.scan_classification_repository import ScanClassificationRepository
from poseidon.backend.database.repositories.model_deployment_repository import ModelDeploymentRepository
from poseidon.backend.database.models.enums import ScanStatus, ScanImageStatus, CameraStatus
from poseidon.backend.core.config import settings
from poseidon.state.auth import AuthState

from poseidon.backend.core.config import settings

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
            
            # Get the deployment record to extract the correct deployment_id
            deployment = await ModelDeploymentRepository.get_by_id(self.selected_deployment_id)
            if not deployment:
                self.error = "Deployment not found"
                return
            
            # Extract the actual deployment_id from deployment_config
            deployment_id = None
            if hasattr(deployment, 'deployment_config') and deployment.deployment_config:
                deployment_id = deployment.deployment_config.get('deployment_id')
            
            if not deployment_id:
                self.error = "Deployment ID not found in deployment configuration"
                return
            
            # Prepare request payload with the correct deployment_id
            payload = {
                "deployment_id": deployment_id,
                "timeout": 30.0
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.MODEL_SERVER_URL}/inference/run",
                    json=payload,
                    timeout=35.0
                )
                
                if response.status_code == 200:
                    response_data = response.json() 
                else:
                    raise Exception(f"API returned {response.status_code}: {response.text}")
            
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
            api_camera_ids = list(results.keys())
            
            # Proactive camera configuration diagnosis for debugging
            if hasattr(deployment, 'camera_ids') and deployment.camera_ids:
                diagnosis = await self._diagnose_camera_configuration(deployment, api_camera_ids)
                print(f"Camera configuration diagnosis: {diagnosis}")
            
            for camera_id, camera_result in results.items():
                if camera_result.get("status") == "success":
                    try:
                        # Try to find camera by camera_id in the deployment's camera_ids
                        camera = None
                        camera_search_methods = []
                        
                        if hasattr(deployment, 'camera_ids') and deployment.camera_ids:
                            from poseidon.backend.database.repositories.camera_repository import CameraRepository
                            
                            # Method 1: Try to find camera by name matching the API camera_id
                            for cam_id in deployment.camera_ids:
                                try:
                                    # Convert cam_id to string if it's an ObjectId
                                    cam_id_str = str(cam_id)
                                    potential_camera = await CameraRepository.get_by_id(cam_id_str)
                                    if potential_camera and hasattr(potential_camera, 'name') and potential_camera.name == camera_id:
                                        camera = potential_camera
                                        camera_search_methods.append(f"Found by name match ({camera_id})")
                                        break
                                except Exception as e:
                                    camera_search_methods.append(f"Failed to get camera {cam_id}: {str(e)}")
                                    continue
                            
                            # Method 2: Try to find camera by device_name matching the API camera_id  
                            if not camera:
                                for cam_id in deployment.camera_ids:
                                    try:
                                        cam_id_str = str(cam_id)
                                        potential_camera = await CameraRepository.get_by_id(cam_id_str)
                                        if potential_camera and hasattr(potential_camera, 'device_name') and potential_camera.device_name == camera_id:
                                            camera = potential_camera
                                            camera_search_methods.append(f"Found by device_name match ({camera_id})")
                                            break
                                    except Exception as e:
                                        continue
                            
                            # Method 3: If still not found, check if camera_id itself is a valid ObjectId in the deployment
                            if not camera:
                                try:
                                    if camera_id in [str(cam_id) for cam_id in deployment.camera_ids]:
                                        potential_camera = await CameraRepository.get_by_id(camera_id)
                                        if potential_camera:
                                            camera = potential_camera
                                            camera_search_methods.append(f"Found by direct ID match ({camera_id})")
                                except Exception as e:
                                    camera_search_methods.append(f"Failed direct ID lookup: {str(e)}")
                        
                        # If camera not found, fail with detailed error
                        if not camera:
                            # Get detailed diagnosis of camera configuration
                            diagnosis = await self._diagnose_camera_configuration(deployment, [camera_id])
                            
                            error_details = f"Camera '{camera_id}' not found in deployment '{deployment.id}'. {diagnosis}"
                            
                            if camera_search_methods:
                                error_details += f" Search attempts: {'; '.join(camera_search_methods)}"
                            
                            # Log detailed error for debugging
                            print(f"CAMERA CONFIGURATION ERROR: {error_details}")
                            
                            raise Exception(f"Camera '{camera_id}' not found in deployment. Please ensure the camera is properly configured in the deployment.")
                        
                        
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
                        
                        # Create scan_classification records for each prediction
                        predictions = camera_result.get("predictions", [])
                        for prediction in predictions:
                            classification_data = {
                                "image": scan_image,
                                "scan": scan,
                                "name": prediction.get("class", "Unknown"),
                                "cls_confidence": prediction.get("severity"),  # Using severity instead of confidence
                                "cls_pred_time": camera_result.get("processing_time"),
                                "det_cls": prediction.get("class"),
                            }
                            
                            # Add bounding box if available - format is [x, y, width, height]
                            bbox = prediction.get("bbox")
                            if bbox and len(bbox) == 4:
                                classification_data.update({
                                    "det_x": float(bbox[0]),      # x coordinate
                                    "det_y": float(bbox[1]),      # y coordinate  
                                    "det_w": float(bbox[2]),      # width
                                    "det_h": float(bbox[3])       # height
                                })
                            
                            classification = await ScanClassificationRepository.create(classification_data)
                        
                    except Exception as e:
                        error_message = str(e)
                        
                        # Check if this is a camera configuration error
                        if "Camera" in error_message and "not found" in error_message:
                            # This is a camera configuration issue - bubble it up to the user
                            print(f"CAMERA ERROR for {camera_id}: {error_message}")
                            raise Exception(f"Camera configuration error: {error_message}")
                        else:
                            # Other errors - log and continue
                            print(f"Error creating scan_image/classifications for camera {camera_id}: {error_message}")
                            continue
            
        except Exception as e:
            error_message = str(e)
            
            # Check if this is a camera configuration error that should bubble up
            if "Camera configuration error" in error_message:
                # Re-raise camera configuration errors so they reach the user
                print(f"CRITICAL ERROR: {error_message}")
                raise e
            else:
                # Log other errors but don't fail the entire scan
                print(f"Error creating database records: {error_message}")
                import traceback
                traceback.print_exc()
                # Continue - scan results are still available even if DB records failed
    
    def _calculate_overall_confidence(self, response_data: Dict[str, Any]) -> Optional[float]:
        """Calculate overall confidence from all predictions"""
        all_confidences = []
        results = response_data.get("results", {})
        
        for camera_result in results.values():
            predictions = camera_result.get("predictions", [])
            for prediction in predictions:
                severity = prediction.get("severity")
                if severity is not None:
                    all_confidences.append(severity)
        
        return sum(all_confidences) / len(all_confidences) if all_confidences else None
    
    async def _diagnose_camera_configuration(self, deployment, api_camera_ids: list) -> str:
        """Diagnose camera configuration issues and provide detailed information"""
        diagnosis = []
        
        # Check if deployment has camera_ids
        if not hasattr(deployment, 'camera_ids') or not deployment.camera_ids:
            diagnosis.append("Deployment has no cameras configured")
            return "; ".join(diagnosis)
        
        diagnosis.append(f"Deployment has {len(deployment.camera_ids)} cameras configured: {deployment.camera_ids}")
        diagnosis.append(f"API returned {len(api_camera_ids)} cameras: {api_camera_ids}")
        
        # Check each camera in deployment
        from poseidon.backend.database.repositories.camera_repository import CameraRepository
        
        valid_cameras = []
        invalid_cameras = []
        
        for cam_id in deployment.camera_ids:
            try:
                cam_id_str = str(cam_id)
                camera = await CameraRepository.get_by_id(cam_id_str)
                if camera:
                    valid_cameras.append({
                        'id': cam_id_str,
                        'name': getattr(camera, 'name', 'N/A'),
                        'device_name': getattr(camera, 'device_name', 'N/A'),
                        'status': getattr(camera, 'status', 'N/A')
                    })
                else:
                    invalid_cameras.append(f"{cam_id_str} (not found in database)")
            except Exception as e:
                invalid_cameras.append(f"{cam_id} (error: {str(e)})")
        
        if valid_cameras:
            diagnosis.append(f"Valid cameras: {valid_cameras}")
        if invalid_cameras:
            diagnosis.append(f"Invalid cameras: {invalid_cameras}")
        
        # Check for potential matches
        matches = []
        for api_cam in api_camera_ids:
            for valid_cam in valid_cameras:
                if (valid_cam['name'] == api_cam or 
                    valid_cam['device_name'] == api_cam or 
                    valid_cam['id'] == api_cam):
                    matches.append(f"'{api_cam}' matches camera {valid_cam['id']} ({valid_cam['name']})")
        
        if matches:
            diagnosis.append(f"Potential matches found: {matches}")
        else:
            diagnosis.append("No matches found between API cameras and deployment cameras")
        
        return "; ".join(diagnosis)
    
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