import reflex as rx
import httpx
from typing import List, Dict, Optional, Any
import math
from poseidon.backend.database.repositories.camera_repository import CameraRepository
from poseidon.backend.database.repositories.project_repository import ProjectRepository
from poseidon.backend.database.models.camera import Camera
from poseidon.backend.database.models.organization import Organization
from poseidon.backend.database.models.user import User
from poseidon.state.auth import AuthState
from poseidon.state.base import BaseManagementState
from poseidon.backend.core.config import settings

camera_repo = CameraRepository()
project_repo = ProjectRepository()


class CameraState(BaseManagementState):
    """
    Secure, multi-tenant, role-aware camera state management.
    Handles: camera discovery, assignment, configuration, capture, and streaming,
    all scoped by organization, project, and user role.
    """
    
    # Context
    organization_id: Optional[str] = None
    project_id: Optional[str] = None
    user_id: Optional[str] = None
    is_admin: bool = False
    is_super_admin: bool = False

    # Project selection
    available_projects: List[Dict[str, Any]] = []
    selected_project_name: str = ""

    # Camera data (scoped)
    cameras: List[str] = []  # Names of cameras in current scope
    camera_objs: List[Any] = []  # Full camera objects in current scope
    selected_camera: Optional[str] = None
    camera_config: Dict[str, Any] = {
        "exposure": 1000,
        "gain": 0,
        "trigger_mode": "continuous",
    }
    camera_statuses: Dict[str, str] = {}
    camera_ranges: Dict[str, Dict[str, List[float]]] = {}
    
    # UI state - override base class loading to use is_loading for consistency
    is_loading: bool = False
    config_modal_open: bool = False
    capture_image_data: Optional[str] = None
    capture_loading: bool = False
    stream_url: Optional[str] = None
    is_streaming: bool = False
    
    # Camera Assignment Dialog State
    assignment_dialog_open: bool = False
    assignment_camera_name: str = ""
    assignment_project_id: str = ""
    API_BASE = "http://192.168.50.32:8001"
    
    # Override loading property to use is_loading for camera-specific operations
    @property
    def loading(self) -> bool:
        return self.is_loading
    
    @loading.setter
    def loading(self, value: bool):
        self.is_loading = value
    
    # --- Context and Permissions ---
    async def initialize_context(self):
        """Initialize the context from auth state and load available projects."""
        # Ensure models are rebuilt to prevent forward reference errors
        try:
            from poseidon.backend.database.init import rebuild_all_models
            rebuild_all_models()
        except Exception as e:
            print(f"Warning: Could not rebuild models: {e}")
        
        auth_state = await self.get_auth_state()
        
        if not auth_state.is_authenticated:
            self.set_error("Please log in to access cameras")
            return
        
        self.user_id = auth_state.user_id
        self.organization_id = auth_state.user_organization_id
        self.is_admin = auth_state.is_admin
        self.is_super_admin = auth_state.is_super_admin
        
        # Load available projects
        await self.load_available_projects()
        
        # Load cameras
        await self.fetch_cameras()

    async def load_available_projects(self):
        """Load projects that the user has access to."""
        if not self.organization_id:
            return
        
        self.is_loading = True
        self.clear_messages()
        
        try:
            auth_state = await self.get_auth_state()
            
            if self.is_super_admin:
                # Super admins can see all projects across all organizations
                projects = await project_repo.get_all()
                # Format projects with organization names for super admins
                formatted_projects = []
                for project in projects:
                    # Extract organization info from Link field
                    if hasattr(project, 'organization') and project.organization:
                        org_id = str(project.organization.id)
                        org_name = project.organization.name if hasattr(project.organization, 'name') else "Unknown"
                    else:
                        org_id = ""
                        org_name = "Unknown"
                    formatted_projects.append({
                        "id": str(project.id),
                        "name": f"{project.name} ({org_name})",
                        "organization_id": org_id
                    })
                self.available_projects = formatted_projects
            elif self.is_admin:
                # Admins can see all projects in their organization
                projects = await project_repo.get_by_organization(self.organization_id)
                self.available_projects = []
                for project in projects:
                    # Extract organization info from Link field
                    org_id = ""
                    if hasattr(project, 'organization') and project.organization:
                        org_id = str(project.organization.id)
                    self.available_projects.append({
                        "id": str(project.id), 
                        "name": project.name, 
                        "organization_id": org_id
                    })
            else:
                # Regular users can only see projects they're explicitly assigned to
                user_project_ids = [
                    assignment.get("project_id") 
                    for assignment in auth_state.user_project_assignments
                ]
                projects = []
                for project_id in user_project_ids:
                    project = await project_repo.get_by_id(project_id)
                    if project:
                        # Extract organization info from Link field
                        org_id = ""
                        if hasattr(project, 'organization') and project.organization:
                            org_id = str(project.organization.id)
                        
                        # Check if project belongs to user's organization
                        if org_id == self.organization_id:
                            projects.append(project)
                
                self.available_projects = []
                for project in projects:
                    # Extract organization info from Link field
                    org_id = ""
                    if hasattr(project, 'organization') and project.organization:
                        org_id = str(project.organization.id)
                    self.available_projects.append({
                        "id": str(project.id), 
                        "name": project.name, 
                        "organization_id": org_id
                    })
                
        except Exception as e:
            self.set_error(f"Error loading projects: {str(e)}")
        finally:
            self.is_loading = False

    async def create_default_project(self):
        """Create a default project for the organization."""
        try:
            from poseidon.backend.database.models.project import Project
            from poseidon.backend.database.models.enums import ProjectStatus
            
            # Get the organization
            org = await Organization.find_one(Organization.name == "mindtrace")
            if not org:
                self.set_error("Organization not found")
                return
            
            # Get the current user
            auth_state = await self.get_auth_state()
            user = await User.find_one(User.username == "mindtracesuperadmin")
            if not user:
                self.set_error("User not found")
                return
            
            # Create default project
            project = Project(
                name="Default Project",
                description="Default project for camera management",
                organization=org,
                owner=user,
                status=ProjectStatus.ACTIVE
            )
            await project.save()
            
            # Add to available projects
            self.available_projects.append({
                "id": str(project.id),
                "name": project.name,
                "description": project.description or "",
                "status": project.status,
                "organization_id": str(org.id)
            })
            
            # Auto-select this project
            self.project_id = str(project.id)
            self.selected_project_name = project.name
            
            self.set_success(f"Created default project: {project.name}")
            
        except Exception as e:
            self.set_error(f"Error creating default project: {str(e)}")

    async def save_camera_to_db(self, camera_name: str, status: str):
        """Save camera status to database."""
        try:
            # Parse camera name to get backend and device name
            if ":" not in camera_name:
                return
            
            backend, device_name = camera_name.split(":", 1)
            
            # Get the organization and user
            org = await Organization.find_one(Organization.name == "mindtrace")
            user = await User.find_one(User.username == "mindtracesuperadmin")
            
            if not org or not user:
                return
            
            # Create camera data
            camera_data = {
                "name": camera_name,
                "backend": backend,
                "device_name": device_name,
                "status": status,
                "organization_id": str(org.id),
                "project_id": self.project_id or "",
                "created_by": str(user.id),
                "description": f"Auto-saved {backend} camera",
                "configuration": {}
            }
            
            # Create or update camera in database
            camera_obj = await camera_repo.create_or_update(camera_data)
            if camera_obj:
                # Update camera_objs list
                if camera_obj not in self.camera_objs:
                    self.camera_objs.append(camera_obj)
                    
        except Exception as e:
            # Don't show error to user for background database operations
            pass

    async def load_available_projects_for_assignment(self):
        """Load available projects for assignment dialog without changing current view."""
        if not self.organization_id:
            return
        
        # Save current view state
        current_project_id = self.project_id
        current_project_name = self.selected_project_name
        
        try:
            auth_state = await self.get_auth_state()
            
            if self.is_super_admin:
                # Super admins can see all projects across all organizations
                projects = await project_repo.get_all()
            elif self.is_admin:
                # Admins can see all projects in their organization
                projects = await project_repo.get_by_organization_and_status(self.organization_id, "active")
            else:
                # Regular users can only see projects they're explicitly assigned to
                user_project_ids = [
                    assignment.get("project_id") 
                    for assignment in auth_state.user_project_assignments
                ]
                projects = []
                for project_id in user_project_ids:
                    project = await project_repo.get_by_id(project_id)
                    if project:
                        # Extract organization info from Link field
                        org_id = ""
                        if hasattr(project, 'organization') and project.organization:
                            org_id = str(project.organization.id)
                        
                        # Check if project belongs to user's organization
                        if org_id == self.organization_id:
                            projects.append(project)
            
            self.available_projects = []
            for project in projects:
                # Extract organization info from Link field
                org_id = ""
                if hasattr(project, 'organization') and project.organization:
                    org_id = str(project.organization.id)
                
                self.available_projects.append({
                    "id": str(project.id),
                    "name": project.name,
                    "description": project.description or "",
                    "status": project.status,
                    "organization_id": org_id
                })
            
            # Restore current view state (don't auto-select first project)
            self.project_id = current_project_id
            self.selected_project_name = current_project_name
                
        except Exception as e:
            self.set_error(f"Error loading projects: {str(e)}")

    async def select_project(self, project_id: str):
        """Select a project and load its cameras."""
        self.project_id = project_id
        
        # Find project name for display
        for project in self.available_projects:
            if project["id"] == project_id:
                self.selected_project_name = project["name"]
                break
        
        # Load cameras for this project
        await self.fetch_cameras()

    async def select_project_by_name(self, project_name: str):
        """Select a project by name and load its cameras."""
        # Handle "All Cameras" option for admins and super admins
        if ((project_name == "All Cameras (Super Admin)" and self.is_super_admin) or 
            (project_name == "All Cameras (Admin)" and self.is_admin)):
            self.selected_project_name = project_name
            self.project_id = None  # Clear project ID to show all cameras
            await self.fetch_cameras()
            return
            
        # Find project ID by name
        for project in self.available_projects:
            if project["name"] == project_name:
                await self.select_project(project["id"])
                break

    async def set_scope(self, organization_id: str, project_id: str):
        """Set the current org/project/user/role context."""
        self.organization_id = organization_id
        self.project_id = project_id
        auth_state = await self.get_auth_state()
        self.user_id = getattr(auth_state, 'user_id', None)
        self.is_admin = getattr(auth_state, 'is_admin', False)
        self.is_super_admin = getattr(auth_state, 'is_super_admin', False)

    def is_camera_in_scope(self, camera_name: str) -> bool:
        """Check if a camera is in the current org/project scope."""
        return camera_name in self.cameras

    def can_assign(self) -> bool:
        """Check if current user can assign/unassign cameras (admin only)."""
        return self.is_admin or self.is_super_admin

    def can_configure(self, camera_name: str) -> bool:
        """Check if user can configure/capture/stream this camera."""
        return self.is_camera_in_scope(camera_name)
    
    @rx.var
    def can_configure_selected(self) -> bool:
        """Check if user can configure the currently selected camera."""
        if not self.selected_camera:
            return False
        return self.is_camera_in_scope(self.selected_camera)
    

    
    @rx.var
    def project_names(self) -> List[str]:
        """Get list of project names for dropdown."""
        return [project["name"] for project in self.available_projects]

    # --- Camera Fetching ---
    async def fetch_cameras(self):
        """Fetch cameras based on project selection and admin toggle."""
        if not self.organization_id:
            self.set_error("No organization selected")
            return
            
        self.is_loading = True
        self.clear_messages()
        
        try:
            # First, fetch all discovered cameras from hardware API
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.API_BASE}/cameras/discover")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        discovered_cameras = data.get("data", [])
                        
                        # Filter cameras based on project selection
                        if self.project_id:
                            # Show only cameras assigned to the selected project
                            project_cameras = await camera_repo.get_by_project_id(self.project_id)
                            # Filter discovered cameras to only show those assigned to this project
                            project_camera_names = [cam.name for cam in project_cameras]
                            self.cameras = [cam for cam in discovered_cameras if cam in project_camera_names]
                            self.camera_objs = project_cameras
                            self.set_success(f"Found {len(self.cameras)} cameras for selected project")
                        elif self.selected_project_name in ["All Cameras (Super Admin)", "All Cameras (Admin)"]:
                            # Show all discovered cameras for admin/super admin
                            self.cameras = discovered_cameras
                            
                            # Load database assignment information for all discovered cameras
                            all_cameras_from_db = await camera_repo.get_all()
                            self.camera_objs = all_cameras_from_db
                            
                            self.set_success(f"Showing all {len(discovered_cameras)} discovered cameras")
                        else:
                            # No project selected, show empty list
                            self.cameras = []
                            self.set_success("Please select a project to view cameras")
            
                        # Initialize camera statuses for visible cameras
                        for camera in self.cameras:
                            if camera not in self.camera_statuses:
                                self.camera_statuses[camera] = "not_initialized"
            
                        # Load projects for assignment functionality
                        await self.load_projects_for_camera_display()
            
                        # Refresh camera statuses from API
                        await self.refresh_camera_statuses()
                        
                    else:
                        self.set_error(data.get("message", "Failed to discover cameras"))
                else:
                    self.set_error(f"Failed to discover cameras: {response.status_code}")
            
        except Exception as e:
            self.set_error(f"Error fetching cameras: {str(e)}")
        finally:
            self.is_loading = False

    # --- Camera Assignment (Admin Only) ---
    async def assign_camera_to_project(self, camera_id: str, organization_id: str, project_id: str):
        """Assign a camera to an organization and project (admin only)."""
        if not self.can_assign():
            self.set_error("Access denied: Admin privileges required")
            return
        
        async def perform_assignment():
            updated_camera = await camera_repo.assign_to_project(camera_id, organization_id, project_id)
            if updated_camera:
                await self.fetch_cameras()
                return True
            else:
                self.set_error("Failed to assign camera (not found)")
                return False

        await self.handle_async_operation(
            perform_assignment,
            f"Camera assigned to project {project_id} in org {organization_id}"
        )

    async def unassign_camera_from_project(self, camera_id: str):
        """Unassign a camera from its organization and project (admin only)."""
        if not self.can_assign():
            self.set_error("Access denied: Admin privileges required")
            return
        
        async def perform_unassignment():
            updated_camera = await camera_repo.unassign_from_project(camera_id)
            if updated_camera:
                await self.fetch_cameras()
                return True
            else:
                self.set_error("Failed to unassign camera (not found)")
                return False

        await self.handle_async_operation(
            perform_unassignment,
            "Camera unassigned from project/organization"
        )

    # --- Camera Configuration (Scoped) ---
    async def load_config_from_db(self, camera_id: str):
        """Load camera config from the database for a camera in scope."""
        if not self.can_configure(camera_id):
            self.set_error("Camera not in current project/organization scope")
            return
        
        async def load_config():
            camera_doc = await camera_repo.get_by_id(camera_id)
            if camera_doc:
                self.camera_config = camera_doc.configuration
                return True
            else:
                self.set_error(f"Camera {camera_id} not found in DB")
                return False

        await self.handle_async_operation(
            load_config,
            f"Loaded config for {camera_id} from DB"
        )

    async def save_config_to_db(self, camera_id: str, configuration: dict):
        """Save camera config to the database for a camera in scope."""
        if not self.can_configure(camera_id):
            self.set_error("Camera not in current project/organization scope")
            return
        
        async def save_config():
            updated_camera = await camera_repo.update_configuration(camera_id, configuration)
            if updated_camera:
                return True
            else:
                self.set_error(f"Failed to save config for {camera_id} to DB (not found or org mismatch)")
                return False

        await self.handle_async_operation(
            save_config,
            f"Saved config for {camera_id} to DB"
        )

    # --- Camera Capture/Streaming (Scoped) ---
    async def capture_image(self):
        """Capture image from the selected camera (scoped)."""
        if not self.selected_camera or not self.can_configure(self.selected_camera):
            self.set_error("No camera selected or not in scope")
            return
        
        self.capture_loading = True
        self.clear_messages()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.API_BASE}/cameras/{self.selected_camera}/capture"
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.capture_image_data = data.get("image_data", "")
                        self.set_success(f"Image captured from {self.selected_camera}")
                    else:
                        self.set_error(data.get("message", f"Failed to capture from {self.selected_camera}"))
                else:
                    self.set_error(f"Failed to capture from {self.selected_camera}: {response.status_code}")
        except Exception as e:
            self.set_error(f"Error capturing from {self.selected_camera}: {str(e)}")
        finally:
            self.capture_loading = False

    async def capture_image_from_card(self, camera: str):
        """Capture image from camera card and upload to GCS."""
        if not self.can_configure(camera):
            self.set_error("Camera not in current project/organization scope")
            return
        
        self.capture_loading = True
        self.clear_messages()
        
        try:
            # Import datetime for timestamp
            from datetime import datetime
            import re
            
            # Create timestamp for filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Clean camera name for filename (remove special characters)
            camera_clean = re.sub(r'[^a-zA-Z0-9]', '_', camera)
            
            # Create filename
            filename = f"{camera_clean}_{timestamp}.jpg"
            
            # Prepare capture request with GCS upload
            capture_payload = {
                "gcs_bucket": settings.GCP_BUCKET_NAME,
                "gcs_path": f"test_capture/{filename}",
                "gcs_metadata": {
                    "camera_name": camera,
                    "capture_type": "test_capture",
                    "project": self.selected_project_name,
                    "organization": self.organization_id,
                    "captured_by": self.user_id,
                    "timestamp": timestamp
                },
                "return_image": False  # Don't return image data to reduce response size
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.API_BASE}/cameras/{camera}/capture",
                    json=capture_payload,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        gcs_uri = data.get("gcs_uri", "")
                        if gcs_uri:
                            # Save image metadata to database
                            await self.save_image_to_database(
                                gcs_uri=gcs_uri,
                                filename=filename,
                                metadata=capture_payload["gcs_metadata"]
                            )
                            self.set_success(f"Image captured and uploaded to GCS: {gcs_uri}")
                            # Refresh images to show the new capture
                            await self.refresh_captured_images()
                        else:
                            self.set_error("Image captured but GCS upload failed")
                    else:
                        self.set_error(data.get("message", f"Failed to capture from {camera}"))
                else:
                    self.set_error(f"Failed to capture from {camera}: {response.status_code}")
        except Exception as e:
            self.set_error(f"Error capturing from {camera}: {str(e)}")
        finally:
            self.capture_loading = False

    async def refresh_captured_images(self):
        """Refresh the captured images list."""
        try:
            # Get ImageState instance and refresh images
            image_state = await self.get_state("ImageState")
            await image_state.load_images(1)  # Reload first page
        except Exception as e:
            print(f"Error refreshing images: {e}")

    async def save_image_to_database(self, gcs_uri: str, filename: str, metadata: dict):
        """Save image metadata to database after GCS upload."""
        try:
            from poseidon.backend.database.repositories.image_repository import ImageRepository
            from datetime import datetime
            
            # Extract GCS path from URI (gcs_uri format: gs://bucket-name/path)
            # We want to store just the relative path within the bucket
            if gcs_uri.startswith("gs://"):
                full_path = gcs_uri[5:]  # Remove "gs://" prefix
                # Extract bucket name and remove it to get relative path
                if "/" in full_path:
                    bucket_name, relative_path = full_path.split("/", 1)
                    gcs_path = relative_path
                else:
                    gcs_path = full_path
            else:
                gcs_path = gcs_uri
            
            # Prepare image data for database
            image_data = {
                "filename": filename,
                "gcp_path": gcs_path,
                "file_size": None,  # Could be extracted from GCS metadata
                "content_type": "image/jpeg",
                "width": None,  # Could be extracted from image
                "height": None,  # Could be extracted from image
                "tags": metadata.get("tags", []),
                "uploaded_by_id": self.user_id,
                "project_id": self.project_id,
                "organization_id": self.organization_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            
            # Save to database
            await ImageRepository.create(image_data)
            print(f"Image metadata saved to database: {filename}")
            
        except Exception as e:
            print(f"Error saving image to database: {e}")

    def start_stream(self, camera: str):
        """Start MJPEG video stream for the given camera (scoped)."""
        if not self.can_configure(camera):
            self.set_error("Camera not in current project/organization scope")
            return
        
        # Stop any existing stream first
        if self.is_streaming:
            self.stop_stream()
            
        self.stream_url = f"{self.API_BASE}/cameras/{camera}/stream"
        self.is_streaming = True
        self.selected_camera = camera

    def stop_stream(self):
        """Stop the MJPEG video stream."""
        self.is_streaming = False
        self.stream_url = None

    # --- UI/Modal State ---
    def close_config_modal(self):
        """Close the configuration modal."""
        self.config_modal_open = False
        self.selected_camera = None
        self.camera_config = {"exposure": 1000, "gain": 0, "trigger_mode": "continuous"}
        self.capture_image_data = None
        self.clear_messages()

    def clear_messages(self):
        """Clear error and success messages."""
        self.set_error("")
        self.set_success("")

    def set_config_modal_open(self, open: bool):
        """Set the config modal open state."""
        self.config_modal_open = open
        if not open:
            self.close_config_modal()

    # --- Computed Properties for UI ---
    @rx.var
    def camera_status_badges(self) -> Dict[str, str]:
        badges = {}
        for camera in self.cameras:
            status = self.camera_statuses.get(camera, "not_initialized")
            if status == "available":
                badges[camera] = "Available"
            elif status == "unavailable":
                badges[camera] = "Unavailable"
            else:
                badges[camera] = "Not Initialized"
        return badges
    
    @rx.var
    def camera_status_colors(self) -> Dict[str, str]:
        colors = {}
        for camera in self.cameras:
            status = self.camera_statuses.get(camera, "not_initialized")
            if status == "available":
                colors[camera] = "#059669"
            elif status == "unavailable":
                colors[camera] = "#DC2626"
            else:
                colors[camera] = "#6B7280"
        return colors
    
    @rx.var
    def current_camera_ranges(self) -> Dict[str, List[float]]:
        """Get ranges for the currently selected camera."""
        if not self.selected_camera:
            return {"exposure": [31, 1000000], "gain": [0, 24]}
        
        ranges = self.camera_ranges.get(self.selected_camera, {})
        return {
            "exposure": ranges.get("exposure", [31, 1000000]),
            "gain": ranges.get("gain", [0, 24])
        }
    
    @rx.var
    def exposure_slider_value(self) -> int:
        """Get current exposure slider value (0-100) for log scale."""
        if not self.selected_camera:
            return 50  # Default middle position
        
        current_exp = self.camera_config.get("exposure", 1000)
        ranges = self.camera_ranges.get(self.selected_camera, {})
        exposure_range = ranges.get("exposure", [31, 1000000])
        
        min_exp = float(exposure_range[0])
        max_exp = float(exposure_range[1])
        
        if current_exp <= min_exp:
            return 0
        if current_exp >= max_exp:
            return 100
        
        min_log = math.log10(min_exp)
        max_log = math.log10(max_exp)
        current_log = math.log10(current_exp)
        
        slider_value = int(100 * (current_log - min_log) / (max_log - min_log))
        return max(0, min(100, slider_value))
    
    @rx.var
    def exposure_display_value(self) -> int:
        """Get current exposure value for display."""
        return int(self.camera_config.get("exposure", 1000))
    
    @rx.var
    def exposure_min_value(self) -> int:
        """Get minimum exposure value for display."""
        if not self.selected_camera:
            return 31
        
        ranges = self.camera_ranges.get(self.selected_camera, {})
        exposure_range = ranges.get("exposure", [31, 1000000])
        return int(exposure_range[0])
    
    @rx.var
    def exposure_max_value(self) -> int:
        """Get maximum exposure value for display."""
        if not self.selected_camera:
            return 1000000
        
        ranges = self.camera_ranges.get(self.selected_camera, {})
        exposure_range = ranges.get("exposure", [31, 1000000])
        return int(exposure_range[1])
    
    @rx.var
    def project_names(self) -> List[str]:
        """Get list of project names for select dropdown."""
        names = [project["name"] for project in self.available_projects]
        # Add "All Cameras" option for admins and super admins
        if self.is_admin or self.is_super_admin:
            if self.is_super_admin:
                names.insert(0, "All Cameras (Super Admin)")
            else:
                names.insert(0, "All Cameras (Admin)")
        return names
    
    async def _fetch_discovered_cameras_for_super_admin(self):
        """Fetch discovered cameras from hardware API for super admin when no cameras in DB."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.API_BASE}/cameras/discover")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        discovered_cameras = data.get("data", [])
                        self.cameras = discovered_cameras
                        # Clear camera_objs since these are not from database
                        self.camera_objs = []
                        # Initialize camera statuses
                        for camera in discovered_cameras:
                            self.camera_statuses[camera] = "not_initialized"
        except Exception as e:
            self.set_error(f"Error fetching discovered cameras: {str(e)}")
    
    async def assign_camera_to_organization(self, camera_name: str):
        """Assign a discovered camera to the current organization (super admin only)."""
        if not self.is_super_admin:
            self.set_error("Only super admins can assign cameras to organizations")
            return
        
        if not self.organization_id:
            self.set_error("No organization selected")
            return
        
        self.is_loading = True
        self.clear_messages()
        
        try:
            # Parse camera name to get backend and device name
            if ":" not in camera_name:
                self.set_error("Invalid camera name format")
                return
            
            backend, device_name = camera_name.split(":", 1)
            
            # Create camera data
            camera_data = {
                "name": camera_name,
                "backend": backend,
                "device_name": device_name,
                "status": "active",
                "organization_id": self.organization_id,
                "project_id": "",  # Unassigned to project initially
                "created_by": self.user_id or "unknown",
                "description": f"Auto-assigned {backend} camera",
                "configuration": {}
            }
            
            # Create or update camera in database
            camera_obj = await camera_repo.create_or_update(camera_data)
            if camera_obj:
                self.set_success(f"Camera {camera_name} assigned to organization successfully")
                # Refresh cameras to show the newly assigned camera
                await self.fetch_cameras()
            else:
                self.set_error(f"Failed to assign camera {camera_name} to organization")
                
        except Exception as e:
            self.set_error(f"Error assigning camera: {str(e)}")
        finally:
            self.is_loading = False
    
    async def fetch_camera_list(self):
        """Fetch the list of available cameras."""
        # Initialize context first
        await self.initialize_context()
        
        # Super admins can fetch cameras without project selection
        if not self.project_id and not self.is_super_admin:
            self.set_error("Please select a project first")
            return
        
        self.is_loading = True
        self.clear_messages()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.API_BASE}/cameras/discover")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        discovered_cameras = data.get("data", [])
                        
                        # Filter to only show cameras assigned to current project
                        await self.fetch_cameras()
                        
                        # Initialize all discovered cameras as not_initialized
                        for camera in discovered_cameras:
                            if camera not in self.camera_statuses:
                                self.camera_statuses[camera] = "not_initialized"
                        
                        if self.is_super_admin and not self.project_id:
                            self.set_success(f"Found {len(discovered_cameras)} total cameras, {len(self.cameras)} in organization")
                        else:
                            self.set_success(f"Found {len(discovered_cameras)} total cameras, {len(self.cameras)} assigned to {self.selected_project_name}")
                    else:
                        self.set_error(data.get("message", "Failed to fetch cameras"))
                else:
                    self.set_error(f"Failed to fetch cameras: {response.status_code}")
        except Exception as e:
            self.set_error(f"Error fetching cameras: {str(e)}")
        finally:
            self.is_loading = False
    
    async def initialize_camera(self, camera: str):
        """Initialize a camera and update its status."""
        if not self.can_configure(camera):
            self.set_error("Camera not in current project scope")
            return
            
        self.is_loading = True
        self.clear_messages()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.API_BASE}/cameras/{camera}/initialize"
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.camera_statuses[camera] = "available"
                        self.set_success(f"Camera {camera} initialized successfully")
                        
                        # Save camera to database
                        await self.save_camera_to_db(camera, "active")
                    else:
                        self.camera_statuses[camera] = "unavailable"
                        self.set_error(data.get("message", f"Failed to initialize {camera}"))
                        
                        # Still save to database with inactive status
                        await self.save_camera_to_db(camera, "inactive")
                else:
                    self.camera_statuses[camera] = "unavailable"
                    self.set_error(f"Failed to initialize {camera}: {response.status_code}")
                    
                    # Still save to database with error status
                    await self.save_camera_to_db(camera, "error")
        except Exception as e:
            self.camera_statuses[camera] = "unavailable"
            self.set_error(f"Error initializing {camera}: {str(e)}")
            
            # Still save to database with error status
            await self.save_camera_to_db(camera, "error")
        finally:
            self.is_loading = False
    
    async def close_camera(self, camera: str):
        """Close a specific camera and update its status."""
        if not self.can_configure(camera):
            self.set_error("Camera not in current project scope")
            return
            
        self.is_loading = True
        self.clear_messages()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(f"{self.API_BASE}/cameras/{camera}")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.camera_statuses[camera] = "not_initialized"
                        self.set_success(f"Camera {camera} closed successfully")
                        
                        # Update camera status in database
                        await self.save_camera_to_db(camera, "inactive")
                        
                        # If the closed camera was selected, clear the selection
                        if self.selected_camera == camera:
                            self.selected_camera = None
                            self.config_modal_open = False
                            self.camera_config = {"exposure": 1000, "gain": 0}
                            self.capture_image_data = None
                    else:
                        self.set_error(data.get("message", f"Failed to close {camera}"))
                else:
                    self.set_error(f"Failed to close {camera}: {response.status_code}")
        except Exception as e:
            self.set_error(f"Error closing {camera}: {str(e)}")
        finally:
            self.is_loading = False
    
    async def close_all_cameras(self):
        """Close all active cameras and update their statuses."""
        self.is_loading = True
        self.clear_messages()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(f"{self.API_BASE}/cameras")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        # Update all camera statuses to not_initialized
                        for camera in self.cameras:
                            self.camera_statuses[camera] = "not_initialized"
                        
                        # Clear selection and modal if any camera was selected
                        if self.selected_camera:
                            self.selected_camera = None
                            self.config_modal_open = False
                            self.camera_config = {"exposure": 1000, "gain": 0}
                            self.capture_image_data = None
                        
                        self.set_success(data.get("message", "All cameras closed successfully"))
                    else:
                        self.set_error(data.get("message", "Failed to close all cameras"))
                else:
                    self.set_error(f"Failed to close all cameras: {response.status_code}")
        except Exception as e:
            self.set_error(f"Error closing all cameras: {str(e)}")
        finally:
            self.is_loading = False
    
    async def refresh_camera_statuses(self):
        """Refresh the status of all cameras by checking which ones are active."""
        self.is_loading = True
        self.clear_messages()
        
        try:
            async with httpx.AsyncClient() as client:
                # Get list of active cameras
                response = await client.get(f"{self.API_BASE}/cameras/active")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        active_cameras = data.get("data", [])
                        
                        # Update status for all cameras
                        for camera in self.cameras:
                            if camera in active_cameras:
                                self.camera_statuses[camera] = "available"
                            else:
                                self.camera_statuses[camera] = "not_initialized"
                        
                        self.set_success(f"Refreshed camera statuses. {len(active_cameras)} cameras active.")
                    else:
                        self.set_error(data.get("message", "Failed to refresh camera statuses"))
                else:
                    self.set_error(f"Failed to refresh camera statuses: {response.status_code}")
        except Exception as e:
            self.set_error(f"Error refreshing camera statuses: {str(e)}")
        finally:
            self.is_loading = False

    async def set_exposure_from_slider(self, slider_value: int):
        """Convert slider value (0-100) to real exposure value and update."""
        if not self.selected_camera:
            return
        
        ranges = self.camera_ranges.get(self.selected_camera, {})
        exposure_range = ranges.get("exposure", [31, 1000000])
        
        min_exp = float(exposure_range[0])
        max_exp = float(exposure_range[1])
        
        min_log = math.log10(min_exp)
        max_log = math.log10(max_exp)
        
        # Convert slider value (0-100) to log value
        log_value = min_log + (max_log - min_log) * (slider_value / 100)
        real_value = int(10 ** log_value)
        
        # Update exposure value
        self.camera_config["exposure"] = real_value
        
        # Call backend API
        await self.update_config_value("exposure", real_value)

    async def fetch_camera_ranges(self, camera: str):
        """Fetch exposure and gain ranges for a camera."""
        try:
            async with httpx.AsyncClient() as client:
                # Fetch exposure range
                exposure_response = await client.get(f"{self.API_BASE}/cameras/{camera}/exposure/range")
                if exposure_response.status_code == 200:
                    exposure_data = exposure_response.json()
                    if exposure_data.get("success"):
                        exposure_range = exposure_data.get("data", [31, 1000000])
                        if camera not in self.camera_ranges:
                            self.camera_ranges[camera] = {}
                        self.camera_ranges[camera]["exposure"] = exposure_range
                    else:
                        # Failed to get exposure range, will use defaults
                        pass
                else:
                    # Exposure range request failed, will use defaults
                    pass
                
                # Fetch gain range
                gain_response = await client.get(f"{self.API_BASE}/cameras/{camera}/gain/range")
                if gain_response.status_code == 200:
                    gain_data = gain_response.json()
                    if gain_data.get("success"):
                        gain_range = gain_data.get("data", [0, 24])
                        if camera not in self.camera_ranges:
                            self.camera_ranges[camera] = {}
                        self.camera_ranges[camera]["gain"] = gain_range
                    else:
                        # Failed to get gain range, will use defaults
                        pass
                else:
                    # Gain range request failed, will use defaults
                    pass
                        
        except Exception as e:
            # Use default ranges if fetching fails
            if camera not in self.camera_ranges:
                self.camera_ranges[camera] = {}
            self.camera_ranges[camera]["exposure"] = [31, 1000000]
            self.camera_ranges[camera]["gain"] = [0, 24]
    
    async def fetch_trigger_mode(self, camera: str):
        """Fetch the current trigger mode for a camera."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.API_BASE}/cameras/{camera}/trigger-mode")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.camera_config["trigger_mode"] = data.get("data", "continuous")
                    else:
                        self.set_error(data.get("message", "Failed to get trigger mode"))
                else:
                    self.set_error(f"Failed to get trigger mode: {response.status_code}")
        except Exception as e:
            self.set_error(f"Error fetching trigger mode: {str(e)}")

    async def set_trigger_mode(self, mode: str):
        """Set the trigger mode for the selected camera."""
        if not self.selected_camera:
            self.set_error("No camera selected")
            return
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.API_BASE}/cameras/{self.selected_camera}/trigger-mode",
                    json={"mode": mode}
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.camera_config["trigger_mode"] = mode
                        self.set_success(f"Trigger mode set to {mode}")
                    else:
                        self.set_error(data.get("message", f"Failed to set trigger mode to {mode}"))
                else:
                    self.set_error(f"Failed to set trigger mode: {response.status_code}")
        except Exception as e:
            self.set_error(f"Error setting trigger mode: {str(e)}")

    async def open_camera_config(self, camera: str):
        """Open camera configuration modal and fetch camera data."""
        if not self.can_configure(camera):
            self.set_error("Camera not in current project scope")
            return
        
        # Stop any existing stream before opening config
        if self.is_streaming:
            self.stop_stream()
            
        self.selected_camera = camera
        self.config_modal_open = True
        try:
            # Fetch camera ranges for sliders
            await self.fetch_camera_ranges(camera)
            await self.fetch_trigger_mode(camera)  # Fetch trigger mode as well
            # Get current camera values
            async with httpx.AsyncClient() as client:
                # Get current exposure
                exposure_response = await client.get(f"{self.API_BASE}/cameras/{camera}/exposure")
                if exposure_response.status_code == 200:
                    exposure_data = exposure_response.json()
                    if exposure_data.get("success"):
                        self.camera_config["exposure"] = exposure_data.get("data", 1000)
                # Get current gain
                gain_response = await client.get(f"{self.API_BASE}/cameras/{camera}/gain")
                if gain_response.status_code == 200:
                    gain_data = gain_response.json()
                    if gain_data.get("success"):
                        self.camera_config["gain"] = gain_data.get("data", 0)
        except Exception as e:
            self.set_error(f"Error opening camera config: {str(e)}")
    
    async def update_config_value(self, key: str, value: Any):
        """Update a configuration value and apply it to the camera."""
        self.camera_config[key] = value
        if not self.selected_camera:
            return
        try:
            async with httpx.AsyncClient() as client:
                if key == "exposure":
                    response = await client.put(
                        f"{self.API_BASE}/cameras/{self.selected_camera}/exposure",
                        json={"exposure": value}
                    )
                elif key == "gain":
                    response = await client.put(
                        f"{self.API_BASE}/cameras/{self.selected_camera}/gain",
                        json={"gain": value}
                    )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.set_success(f"{key.title()} updated to {value}")
                    else:
                        self.set_error(data.get("message", f"Failed to update {key}"))
                else:
                    self.set_error(f"Failed to update {key}: {response.status_code}")
        except Exception as e:
            self.set_error(f"Error updating {key}: {str(e)}")
    
    async def apply_config(self):
        """Apply all current configuration values to the selected camera using existing setters."""
        if not self.selected_camera:
            self.set_error("No camera selected")
            return
        
        if not self.can_configure(self.selected_camera):
            self.set_error("Camera not in current project/organization scope")
            return
        
        self.is_loading = True
        self.clear_messages()
        
        try:
            # Apply each configuration value using existing setters
            for key, value in self.camera_config.items():
                if key == "exposure":
                    # Use the existing update_config_value method for exposure
                    await self.update_config_value("exposure", value)
                elif key == "gain":
                    # Use the existing update_config_value method for gain
                    await self.update_config_value("gain", value)
                elif key == "trigger_mode":
                    # Use the existing set_trigger_mode method
                    await self.set_trigger_mode(value)
                
                # Check if there was an error from the setter
                if self.error:
                    return  # Stop if any setter failed
            
            # Save configuration to database after all values are applied
            await self.save_config_to_db(self.selected_camera, self.camera_config)
            
            # Only show success if no errors occurred
            if not self.error:
                self.set_success(f"Configuration applied to {self.selected_camera}")
                
        except Exception as e:
            self.set_error(f"Error applying configuration: {str(e)}")
        finally:
            self.is_loading = False

    async def export_config_to_json(self, camera: str, path: str):
        """Export camera config to a JSON file via API."""
        self.is_loading = True
        self.clear_messages()
        try:
            url = f"{self.API_BASE}/cameras/{camera}/config/export"
            payload = {"config_path": path}
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.set_success(f"Exported config for {camera} to {path}")
                    else:
                        self.set_error(data.get("message", f"Failed to export config for {camera} to {path}"))
                else:
                    self.set_error(f"Failed to export config for {camera}: {response.status_code}")
        except Exception as e:
            self.set_error(f"Error exporting config: {str(e)}")
        finally:
            self.is_loading = False

    async def import_config_from_json(self, camera: str, path: str):
        """Import camera config from a JSON file via API."""
        self.is_loading = True
        self.clear_messages()
        try:
            url = f"{self.API_BASE}/cameras/{camera}/config/import"
            payload = {"config_path": path}
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        # Optionally update camera_config if API returns config
                        self.set_success(f"Imported config for {camera} from {path}")
                    else:
                        self.set_error(data.get("message", f"Failed to import config for {camera} from {path}"))
                else:
                    self.set_error(f"Failed to import config for {camera}: {response.status_code}")
        except Exception as e:
            self.set_error(f"Error importing config: {str(e)}")
        finally:
            self.is_loading = False 

    async def fetch_cameras_for_scope(self, organization_id: str, project_id: str):
        """Fetch cameras assigned to the given organization and project."""
        self.is_loading = True
        self.clear_messages()
        try:
            camera_objs = await camera_repo.get_by_organization_and_project(organization_id, project_id)
            self.camera_objs = camera_objs
            self.cameras = [cam.name for cam in camera_objs]
            self.set_success(f"Loaded {len(camera_objs)} cameras for this project")
        except Exception as e:
            self.set_error(f"Error fetching cameras: {str(e)}")
        finally:
            self.is_loading = False 

    async def assign_camera_to_project(self, camera_id: str, organization_id: str, project_id: str):
        """Assign a camera to an organization and project (admin only)."""
        auth_state = await self.get_auth_state()
        if not getattr(auth_state, 'is_admin', False) and not getattr(auth_state, 'is_super_admin', False):
            self.set_error("Access denied: Admin privileges required")
            return
        self.is_loading = True
        self.clear_messages()
        try:
            updated_camera = await camera_repo.assign_to_project(camera_id, organization_id, project_id)
            if updated_camera:
                self.set_success(f"Camera assigned to project {project_id} in org {organization_id}")
                await self.fetch_cameras()  # Refresh list
            else:
                self.set_error(f"Failed to assign camera (not found)")
        except Exception as e:
            self.set_error(f"Error assigning camera: {str(e)}")
        finally:
            self.is_loading = False

    async def unassign_camera_from_project(self, camera_id: str):
        """Unassign a camera from its organization and project (admin only)."""
        auth_state = await self.get_auth_state()
        if not getattr(auth_state, 'is_admin', False) and not getattr(auth_state, 'is_super_admin', False):
            self.set_error("Access denied: Admin privileges required")
            return
        self.is_loading = True
        self.clear_messages()
        try:
            updated_camera = await camera_repo.unassign_from_project(camera_id)
            if updated_camera:
                self.set_success(f"Camera unassigned from project/organization")
                await self.fetch_cameras()  # Refresh list
            else:
                self.set_error(f"Failed to unassign camera (not found)")
        except Exception as e:
            self.set_error(f"Error unassigning camera: {str(e)}")
        finally:
            self.is_loading = False

    async def load_projects_for_camera_display(self):
        """Load all projects referenced by cameras for proper assignment display"""
        try:
            # Get all unique project IDs from camera objects
            project_ids = set()
            for cam in self.camera_objs:
                # Extract project ID from Link field
                if hasattr(cam, 'project') and cam.project:
                    project_ids.add(str(cam.project.id))
            
            # Load project details for each referenced project ID
            for project_id in project_ids:
                # Check if project is already in available_projects
                already_loaded = any(project["id"] == project_id for project in self.available_projects)
                
                if not already_loaded:
                    try:
                        project = await project_repo.get_by_id(project_id)
                        if project:
                            # Extract organization info from Link field
                            org_id = ""
                            if hasattr(project, 'organization') and project.organization:
                                org_id = str(project.organization.id)
                            
                            self.available_projects.append({
                                "id": str(project.id),
                                "name": project.name,
                                "description": project.description or "",
                                "status": project.status,
                                "organization_id": org_id
                            })
                    except Exception:
                        # If we can't load the project, continue with others
                        pass
                        
        except Exception as e:
            # Don't fail the whole operation if project loading fails
            pass

    async def refresh_camera_data(self):
        """Refresh camera data without changing current view state."""
        # Save current view state
        current_project_id = self.project_id
        current_project_name = self.selected_project_name
        
        # Refresh camera data
        await self.fetch_cameras()
        
        # Load all projects referenced by cameras for proper display
        await self.load_projects_for_camera_display()
        
        # Restore view state if it was changed
        if current_project_id != self.project_id:
            self.project_id = current_project_id
            self.selected_project_name = current_project_name

    # Camera Assignment Dialog Methods
    async def open_camera_assignment_dialog(self, camera_name: str):
        """Open camera assignment dialog for a specific camera"""
        self.assignment_camera_name = camera_name
        self.assignment_project_id = ""
        self.assignment_dialog_open = True
        # Load available projects for assignment without changing current view
        await self.load_available_projects_for_assignment()

    def close_camera_assignment_dialog(self):
        """Close camera assignment dialog"""
        self.assignment_camera_name = ""
        self.assignment_project_id = ""
        self.assignment_dialog_open = False

    def set_camera_assignment_dialog_open(self, open: bool):
        """Set camera assignment dialog open state"""
        self.assignment_dialog_open = open
        if not open:
            self.close_camera_assignment_dialog()

    def set_assignment_project(self, project_id: str):
        """Set the project for camera assignment"""
        self.assignment_project_id = project_id

    def set_assignment_project_by_name(self, project_name: str):
        """Set assignment project by name"""
        if self.is_super_admin and " (" in project_name:
            # Extract project name from "Project Name (Organization)" format
            actual_project_name = project_name.split(" (")[0]
            for project in self.available_projects:
                if project["name"] == actual_project_name:
                    self.assignment_project_id = project["id"]
                    break
        else:
            # Regular format for admins and users
            for project in self.available_projects:
                if project["name"] == project_name:
                    self.assignment_project_id = project["id"]
                    break

    async def assign_camera_to_project_from_dialog(self):
        """Assign camera to project using dialog data"""
        try:
            self.is_loading = True
            self.clear_messages()
            
            if not self.assignment_camera_name or not self.assignment_project_id:
                self.set_error("Camera and project are required")
                return
                
            if not self.can_assign():
                self.set_error("Access denied: Admin privileges required")
                return
            
            # Get the project's organization ID
            project = await project_repo.get_by_id(self.assignment_project_id)
            if not project:
                self.set_error("Project not found")
                return
            
            # Extract organization info from Link field
            project_organization_id = ""
            if hasattr(project, 'organization') and project.organization:
                project_organization_id = str(project.organization.id)
            
            if not project_organization_id:
                self.set_error("Project organization not found")
                return
            
            # Check if camera exists in database
            camera_repo = CameraRepository()
            camera = await camera_repo.get_by_name(self.assignment_camera_name, project_organization_id)
            
            if not camera:
                # Camera doesn't exist in database, create it
                # Parse camera name to extract backend and device name
                if ":" in self.assignment_camera_name:
                    backend, device_name = self.assignment_camera_name.split(":", 1)
                else:
                    backend = "unknown"
                    device_name = self.assignment_camera_name
                
                # Get current user for created_by field
                auth_state = await self.get_auth_state()
                user_id = auth_state.user_id if auth_state else None
                
                camera_data = {
                    "name": self.assignment_camera_name,
                    "backend": backend,
                    "device_name": device_name,
                    "organization_id": project_organization_id,  # Use project's organization
                    "project_id": self.assignment_project_id,
                    "created_by_id": user_id,
                    "description": f"Auto-created camera from hardware discovery",
                    "is_active": True
                }
                await camera_repo.create_or_update(camera_data)
                self.set_success(f"Camera {self.assignment_camera_name} created and assigned to project")
            else:
                # Camera exists, update assignment
                await camera_repo.assign_to_project(camera.name, self.assignment_project_id, project_organization_id)
                self.set_success(f"Camera {self.assignment_camera_name} assigned to project")
            
            # Close dialog
            self.assignment_dialog_open = False
            self.assignment_camera_name = ""
            self.assignment_project_id = ""
            
            # Refresh camera data without changing view
            await self.refresh_camera_data()
            
        except Exception as e:
            self.set_error(f"Error assigning camera: {str(e)}")
        finally:
            self.is_loading = False

    async def unassign_camera_from_project_by_name(self, camera_name: str):
        """Unassign camera from project by camera name"""
        try:
            self.is_loading = True
            self.clear_messages()
            
            if not self.can_assign():
                self.set_error("Access denied: Admin privileges required")
                return
            
            # Find the camera object to get its ID
            camera_obj = None
            for cam in self.camera_objs:
                if cam.name == camera_name:
                    camera_obj = cam
                    break
            
            if not camera_obj:
                self.set_error("Camera not found in database. Only cameras that are already assigned to projects can be unassigned.")
                return
            
            result = await camera_repo.unassign_from_project(str(camera_obj.id))
            
            if result:
                self.set_success(f"Camera {camera_name} successfully unassigned from project")
                await self.refresh_camera_data()  # Refresh camera list without changing view
            else:
                self.set_error("Failed to unassign camera from project")
            
        except Exception as e:
            self.set_error(f"Failed to unassign camera from project: {str(e)}")
        finally:
            self.is_loading = False

    @rx.var
    def assignment_project_name(self) -> str:
        """Get the name of the project being assigned"""
        for project in self.available_projects:
            if project["id"] == self.assignment_project_id:
                if self.is_super_admin:
                    return f"{project['name']} ({self.get_organization_name(project['organization_id'])})"
                else:
                    return project["name"]
        return ""

    @rx.var
    def available_project_options(self) -> List[str]:
        """Get list of available project names for dropdown"""
        if self.is_super_admin:
            # For super admins, show organization name with project name
            return [f"{project['name']} ({self.get_organization_name(project['organization_id'])})" for project in self.available_projects]
        else:
            # For admins and regular users, just show project name
            return [project["name"] for project in self.available_projects]

    def get_organization_name(self, org_id: str) -> str:
        """Get organization name by ID (simplified for display)"""
        # This is a simplified version - in a real app you might want to cache organization names
        org_names = {
            "SYSTEM": "System",
            "Mindtrace": "Mindtrace", 
            "Adient": "Adient"
        }
        return org_names.get(org_id, org_id)

    @rx.var
    def assignment_camera_current_project(self) -> str:
        """Get the current project name for the assignment camera"""
        for cam in self.camera_objs:
            # Extract project ID from Link field
            cam_project_id = ""
            if hasattr(cam, 'project') and cam.project:
                cam_project_id = str(cam.project.id)
            
            if cam.name == self.assignment_camera_name and cam_project_id:
                for project in self.available_projects:
                    if project["id"] == cam_project_id:
                        return project["name"]
        return "Unassigned"

    @rx.var
    def camera_project_assignments(self) -> Dict[str, str]:
        """Get a mapping of camera names to their project assignments"""
        assignments = {}
        
        for cam in self.camera_objs:
            # Extract project ID from Link field
            cam_project_id = ""
            if hasattr(cam, 'project') and cam.project:
                cam_project_id = str(cam.project.id)
            
            if cam_project_id:
                # First try to find project in available_projects
                project_name = None
                for project in self.available_projects:
                    if project["id"] == cam_project_id:
                        project_name = project["name"]
                        break
                
                if project_name:
                    assignments[cam.name] = project_name
                else:
                    # Project not in available_projects, try to find it in loaded projects
                    for project_id, project_name in self.loaded_project_names.items():
                        if project_id == cam_project_id:
                            assignments[cam.name] = project_name
                            break
                    else:
                        # Still not found, show the project ID
                        assignments[cam.name] = f"Project {cam_project_id}"
        
        # For cameras that are in self.cameras but not in self.camera_objs (not in database yet)
        for camera_name in self.cameras:
            if camera_name not in assignments:
                assignments[camera_name] = "Unassigned"
        
        return assignments
    
    def get_project_name_by_id(self, project_id: str) -> str:
        """Get project name by ID, with fallback for projects not in available_projects"""
        # First check available_projects
        for project in self.available_projects:
            if project["id"] == project_id:
                return project["name"]
        
        # If not found, return a placeholder indicating it's assigned but project details not loaded
        return f"Assigned Project ({project_id[:8]}...)"

    def get_camera_current_project_name(self, camera_name: str) -> str:
        """Get the current project name for any camera by name"""
        for cam in self.camera_objs:
            # Extract project ID from Link field
            cam_project_id = ""
            if hasattr(cam, 'project') and cam.project:
                cam_project_id = str(cam.project.id)
            
            if cam.name == camera_name and cam_project_id:
                return self.get_project_name_by_id(cam_project_id)
        return "Unassigned" 