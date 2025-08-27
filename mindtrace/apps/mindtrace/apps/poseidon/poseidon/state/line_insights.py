"""
Line Insights State Management

Handles state for the Line Insights dashboard including data fetching,
filtering, and aggregation for production line metrics.
"""

import reflex as rx
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from poseidon.state.base import BaseFilterState
from poseidon.backend.database.repositories.scan_repository import ScanRepository
from poseidon.backend.database.repositories.scan_classification_repository import ScanClassificationRepository
from poseidon.backend.database.repositories.camera_repository import CameraRepository
from poseidon.backend.database.models.enums import ScanStatus

# Configuration constants - modify these for different deployments
DEFAULT_PLANT_NAME = "mindtrace"  # Updated to match seeded organization name
DEFAULT_PROJECT_NAME = "Sample Inspection Project"  # Updated to match seeded data
FREQUENT_DEFECTS_LIMIT = 10  # Top N defects to display

# Comprehensive defect types for chart y-axis (static - chart shows only data that exists)
# Updated to include actual defect types from seed data
ALL_DEFECT_TYPES = [
    "Healthy", "Burr", "Defective",  # From seed data
    "Burnthrough", "Skip", "Porosity", "Undercut", "Overlap", 
    "Incomplete Penetration", "Crack", "Spatter", "Distortion", 
    "Unknown", "Other"  # Fallbacks for any unmapped defect types
]


class LineInsightsState(BaseFilterState):
    """State management for Line Insights dashboard."""
    
    # Default plant and line values (replacing dynamic routing)
    plant_id: str = DEFAULT_PLANT_NAME  # Default plant
    line_id: str = ""    # Will be set dynamically to project ID
    project_name: str = ""  # Will be set dynamically to project name
    
    # Global time filtering (affects all charts)
    date_range: str = "last_7_days"  # last_7_days, last_30_days, last_90_days, custom
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    # Chart display options
    # Note: Individual filters removed to show comprehensive trend data
    
    # Available filter options (populated dynamically)
    available_defect_types: List[str] = []
    available_cameras: List[str] = []
    
    @rx.var
    def defect_types_with_all(self) -> List[str]:
        """Get defect types with 'all' option prepended."""
        return ["all"] + self.available_defect_types
    
    @rx.var  
    def cameras_with_all(self) -> List[str]:
        """Get cameras with 'all' option prepended."""
        return ["all"] + self.available_cameras
    
    
    
    # Store defect types for camera matrix chart
    camera_chart_defect_types: List[str] = []
    
    # Chart data
    parts_scanned_data: List[Dict[str, Any]] = []
    defect_rate_data: List[Dict[str, Any]] = []
    frequent_defects_data: List[Dict[str, Any]] = []
    camera_defect_matrix_data: List[Dict[str, Any]] = []
    
    # Summary metrics
    total_parts_scanned: int = 0
    total_defects_found: int = 0
    average_defect_rate: float = 0.0
    active_cameras: int = 0
    
    # Loading states for individual charts
    loading_parts_chart: bool = False
    loading_defect_chart: bool = False
    loading_frequent_chart: bool = False
    loading_matrix_chart: bool = False
    
    async def set_date_range(self, range_type: str):
        """Set the date range for filtering data."""
        self.date_range = range_type
        now = datetime.now()
        
        if range_type == "last_7_days":
            self.start_date = now - timedelta(days=7)
            self.end_date = now
        elif range_type == "last_30_days":
            self.start_date = now - timedelta(days=30)
            self.end_date = now
        elif range_type == "last_90_days":
            self.start_date = now - timedelta(days=90)
            self.end_date = now
        # For custom range, dates are set separately
        
        # Refresh data when date range changes
        await self.load_dashboard_data()
    
    # Filter methods removed to maintain chart clarity and comprehensive data view
    
    async def set_custom_date_range(self, start: str, end: str):
        """Set custom date range."""
        try:
            self.start_date = datetime.fromisoformat(start)
            self.end_date = datetime.fromisoformat(end)
            self.date_range = "custom"
            await self.load_dashboard_data()
        except ValueError:
            self.set_error("Invalid date format")
    
    @rx.var
    def formatted_date_range(self) -> str:
        """Get formatted date range string for display."""
        if self.start_date and self.end_date:
            return f"{self.start_date.strftime('%b %d, %Y')} - {self.end_date.strftime('%b %d, %Y')}"
        return "Select date range"
    
    async def on_mount(self):
        """Called when the page is mounted. Load initial data."""
        # First, find the project if not already set
        if not self.line_id:
            await self.find_project_by_name()
        
        # Load filter options first (needed for UI)
        await self.load_filter_options()
        
        # Set default date range if not set
        if not self.start_date:
            await self.set_date_range("last_7_days")
        else:
            # Load dashboard data if date range already set
            await self.load_dashboard_data()
    
    async def find_project_by_name(self, project_name: str = DEFAULT_PROJECT_NAME):
        """Find and set the project ID dynamically by name."""
        try:
            from poseidon.backend.database.repositories.project_repository import ProjectRepository
            
            # Get all projects and find the one with matching name
            projects = await ProjectRepository.get_all()
            target_project = next((p for p in projects if p.name == project_name), None)
            
            if target_project:
                self.line_id = str(target_project.id)
                self.project_name = target_project.name
            
        except Exception as e:
            # Project lookup failed, line_id remains empty
            pass
    
    async def load_filter_options(self):
        """Load available options for chart filters."""
        try:
            # Skip if no project ID found
            if not self.line_id:
                self.available_defect_types = []
                self.available_cameras = []
                return
            
            # Get all defect types from classifications
            classifications = await ScanClassificationRepository.get_by_project_and_date_range(
                self.line_id, None, None  # Get all time to populate complete filter list
            )
            
            # Extract unique defect types
            defect_types = set()
            for cls in classifications:
                if cls.name:
                    defect_types.add(cls.name)
            
            self.available_defect_types = sorted(list(defect_types))
            
            # Get all cameras for this project  
            cameras = await CameraRepository.get_by_project(self.line_id) if self.line_id else []
            camera_names = set()
            for camera in cameras:
                if camera.name:
                    camera_names.add(camera.name)
            
            self.available_cameras = sorted(list(camera_names))
            
        except Exception as e:
            self.available_defect_types = []
            self.available_cameras = []
    
    async def load_dashboard_data(self):
        """Load all dashboard data based on current filters."""
        # Set loading states
        self.loading = True
        self.clear_messages()
        
        try:
            # Load data for each chart in parallel
            await self.load_parts_scanned_data()
            await self.load_defect_rate_data()
            await self.load_frequent_defects_data()
            await self.load_camera_defect_matrix_data()
            
            # Calculate summary metrics
            await self.calculate_summary_metrics()
            
            # Dashboard data loading completed
        except Exception as e:
            self.set_error(f"Failed to load dashboard data: {str(e)}")
        finally:
            self.loading = False
    
    async def load_parts_scanned_data(self):
        """Load data for parts scanned over time chart."""
        self.loading_parts_chart = True
        try:
            # Skip if no project ID
            if not self.line_id:
                self.parts_scanned_data = []
                return
                
            # Get scans for the project within date range
            scans = await ScanRepository.get_by_project_and_date_range(
                self.line_id, 
                self.start_date, 
                self.end_date
            )
            
            # If no data found, show empty
            if not scans or len(scans) == 0:
                self.parts_scanned_data = []
                return
            
            # Aggregate by day
            daily_counts = {}
            for scan in scans:
                date_key = scan.created_at.strftime("%Y-%m-%d")
                if date_key not in daily_counts:
                    daily_counts[date_key] = {"date": date_key, "count": 0, "defects": 0}
                
                daily_counts[date_key]["count"] += 1
                # Check if scan has defects (failed status or defective classification)
                if scan.status == ScanStatus.FAILED or (scan.cls_result and scan.cls_result.lower() == "defective"):
                    daily_counts[date_key]["defects"] += 1
            
            # Convert to list and sort by date
            self.parts_scanned_data = sorted(
                daily_counts.values(),
                key=lambda x: x["date"]
            )
        except Exception as e:
            self.parts_scanned_data = []
        finally:
            self.loading_parts_chart = False
    
    async def load_defect_rate_data(self):
        """Load data for defect rate over time chart."""
        self.loading_defect_chart = True
        try:
            # Skip if no project ID
            if not self.line_id:
                self.defect_rate_data = []
                return
                
            # Get all scans for defect rate calculation
            scans = await ScanRepository.get_by_project_and_date_range(
                self.line_id,
                self.start_date,
                self.end_date
            )
            
            # Return empty if no scan data available
            if not scans or len(scans) == 0:
                self.defect_rate_data = []
                return
            
            # Aggregate defect rates by day based on part-level results
            daily_rates = {}
            for scan in scans:
                date_key = scan.created_at.strftime("%Y-%m-%d")
                if date_key not in daily_rates:
                    daily_rates[date_key] = {
                        "date": date_key,
                        "defective_parts": 0,
                        "total_parts": 0,
                        "defect_rate": 0.0
                    }
                
                daily_rates[date_key]["total_parts"] += 1
                # Count part as defective if scan failed or classified as defective
                if scan.status == ScanStatus.FAILED or (scan.cls_result and scan.cls_result.lower() == "defective"):
                    daily_rates[date_key]["defective_parts"] += 1
            
            # Calculate percentage of defective parts per day
            for date_data in daily_rates.values():
                if date_data["total_parts"] > 0:
                    date_data["defect_rate"] = (
                        date_data["defective_parts"] / date_data["total_parts"] * 100
                    )
            
            self.defect_rate_data = sorted(
                daily_rates.values(),
                key=lambda x: x["date"]
            )
        except Exception as e:
            self.defect_rate_data = []
        finally:
            self.loading_defect_chart = False
    
    async def load_frequent_defects_data(self):
        """Load data for most frequent defects chart."""
        self.loading_frequent_chart = True
        try:
            # Skip if no project ID
            if not self.line_id:
                self.frequent_defects_data = []
                return
                
            # Get classifications and count by defect type - no filter, shows all types for distribution
            classifications = await ScanClassificationRepository.get_by_project_and_date_range(
                self.line_id,
                self.start_date,
                self.end_date
            )
            
            # If no data found, show empty
            if not classifications or len(classifications) == 0:
                self.frequent_defects_data = []
                return
            
            # Count defects by type
            defect_counts = {}
            for cls in classifications:
                defect_type = cls.name or "Unknown"
                defect_counts[defect_type] = defect_counts.get(defect_type, 0) + 1
            
            # Convert to list and sort by count
            self.frequent_defects_data = [
                {"defect_type": defect, "count": count}
                for defect, count in sorted(
                    defect_counts.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:FREQUENT_DEFECTS_LIMIT]  # Top N defects
            ]
        except Exception as e:
            self.frequent_defects_data = []
        finally:
            self.loading_frequent_chart = False
    
    async def load_camera_defect_matrix_data(self):
        """Load data for camera defect matrix chart."""
        self.loading_matrix_chart = True
        try:
            # Skip if no project ID
            if not self.line_id:
                self.camera_defect_matrix_data = []
                return
                
            # Get cameras for the project
            cameras = await CameraRepository.get_by_project(self.line_id)
            
            # If no cameras found, show empty
            if not cameras or len(cameras) == 0:
                self.camera_defect_matrix_data = []
                return
            
            # Get classifications by camera
            matrix_data = []
            has_any_data = False
            
            for camera in cameras:
                # Get all defects for this camera in the time range - no filters for distribution
                camera_defects = await ScanClassificationRepository.get_by_camera_and_date_range(
                    camera.id,
                    self.start_date,
                    self.end_date
                )
                
                
                if camera_defects:
                    has_any_data = True
                
                # Count defects by type for this camera
                defect_counts = {}
                for cls in camera_defects:
                    defect_type = cls.name or "Unknown"
                    defect_counts[defect_type] = defect_counts.get(defect_type, 0) + 1
                
                # Add camera data with fallback name
                camera_name = camera.name if camera.name else f"Camera {str(camera.id)[:8]}"
                camera_data = {
                    "camera": camera_name,
                    **defect_counts
                }
                matrix_data.append(camera_data)
            
            # If we have cameras but no classification data, show empty
            if not has_any_data:
                self.camera_defect_matrix_data = []
                self.camera_chart_defect_types = []
            else:
                self.camera_defect_matrix_data = matrix_data
                
                # Extract defect types dynamically from the data
                all_defect_types = set()
                for camera_data in matrix_data:
                    for key in camera_data.keys():
                        if key != "camera":
                            all_defect_types.add(key)
                self.camera_chart_defect_types = sorted(list(all_defect_types))
                
        except Exception as e:
            self.camera_defect_matrix_data = []
            self.camera_chart_defect_types = []
        finally:
            self.loading_matrix_chart = False
    
    async def calculate_summary_metrics(self):
        """Calculate summary metrics for the dashboard header."""
        try:
            # Total parts scanned
            self.total_parts_scanned = sum(
                day["count"] for day in self.parts_scanned_data
            )
            
            # Defective parts (parts with at least one defect)
            self.total_defects_found = sum(
                day["defects"] for day in self.parts_scanned_data
            )
            
            # Calculate average defect rate as percentage of defective parts
            if self.total_parts_scanned > 0:
                self.average_defect_rate = (
                    self.total_defects_found / self.total_parts_scanned * 100
                )
            else:
                self.average_defect_rate = 0.0
            
            # Active cameras
            cameras = await CameraRepository.get_by_project(self.line_id) if self.line_id else []
            
            if cameras:
                self.active_cameras = len([c for c in cameras if getattr(c, 'is_active', True)])
            else:
                self.active_cameras = 0
                
        except Exception as e:
            self.total_parts_scanned = 0
            self.total_defects_found = 0  
            self.average_defect_rate = 0.0
            self.active_cameras = 0
    