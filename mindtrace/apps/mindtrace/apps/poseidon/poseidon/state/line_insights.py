"""
Line Insights State 

"""

import asyncio
import reflex as rx
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta, timezone

from poseidon.state.base import BaseFilterState
from poseidon.backend.database.repositories.metrics_repository import MetricsRepository
from poseidon.backend.database.repositories.scan_classification_repository import ScanClassificationRepository
from poseidon.backend.database.repositories.camera_repository import CameraRepository

# Configuration constants
DEFAULT_PLANT_NAME = "mindtrace"
DEFAULT_PROJECT_NAME = "Sample Inspection Project"
DEFECT_HISTOGRAM_LIMIT = 10


class LineInsightsState(BaseFilterState):
    """State management for Line Insights dashboard."""

    # Display / context
    project_name: str = ""

    # Global time filtering
    date_range: str = "last_7_days"  # last_1_day, last_7_days, last_30_days, last_90_days, custom
    start_date: Optional[datetime] = None  # timezone-aware UTC
    end_date: Optional[datetime] = None    # timezone-aware UTC (exclusive upper bound)

    # Filter options (populated dynamically)
    available_defect_types: List[str] = []
    available_cameras: List[str] = []

    @rx.var
    def defect_types_with_all(self) -> List[str]:
        return ["all"] + self.available_defect_types

    @rx.var
    def cameras_with_all(self) -> List[str]:
        return ["all"] + self.available_cameras

    # Chart-specific state

    parts_scanned_data: List[Dict[str, Any]] = []
    defect_rate_data: List[Dict[str, Any]] = []
    defect_histogram_data: List[Dict[str, Any]] = []
    weld_defect_rate_data: List[Dict[str, Any]] = []
    healthy_vs_defective_data: List[Dict[str, Any]] = []

    # Summary metrics
    total_parts_scanned: int = 0
    total_defects_found: int = 0
    average_defect_rate: float = 0.0
    active_cameras: int = 0

    # Loading flags

    loading_parts_chart: bool = False
    loading_defect_chart: bool = False
    loading_defect_histogram_chart: bool = False
    loading_weld_chart: bool = False
    loading_healthy_vs_defective_chart: bool = False

    async def set_date_range(self, range_type: str):
        """Set the date range and reload data."""
        self.date_range = range_type
        now = datetime.now(timezone.utc)

        if range_type == "last_1_day":
            self.start_date = now - timedelta(days=1)
            self.end_date = now
        elif range_type == "last_7_days":
            self.start_date = now - timedelta(days=7)
            self.end_date = now
        elif range_type == "last_30_days":
            self.start_date = now - timedelta(days=30)
            self.end_date = now
        elif range_type == "last_90_days":
            self.start_date = now - timedelta(days=90)
            self.end_date = now
        # custom is handled separately

        await self.load_dashboard_data()

    async def set_custom_date_range(self, start: str, end: str):
        """Set custom ISO date range and reload."""
        try:
            # Accept both date-only and datetime ISO strings
            s = datetime.fromisoformat(start)
            e = datetime.fromisoformat(end)
            # Ensure timezone-aware UTC
            if s.tzinfo is None:
                s = s.replace(tzinfo=timezone.utc)
            if e.tzinfo is None:
                e = e.replace(tzinfo=timezone.utc)
            self.start_date, self.end_date = s, e
            self.date_range = "custom"
            await self.load_dashboard_data()
        except ValueError:
            self.set_error("Invalid date format. Use ISO 8601 (e.g., 2025-09-02T00:00:00Z).")

    @rx.var
    def formatted_date_range(self) -> str:
        if self.start_date and self.end_date:
            s = self.start_date.astimezone(timezone.utc).strftime("%b %d, %Y")
            e = self.end_date.astimezone(timezone.utc).strftime("%b %d, %Y")
            return f"{s} - {e}"
        return "Select date range"

    async def on_mount(self):
        """Initialize project, filters, and initial data."""
        if not self.line_id:
            await self.find_project_by_name()
        await self.load_filter_options()
        if not self.start_date:
            await self.set_date_range("last_7_days")
        else:
            await self.load_dashboard_data()

    async def find_project_by_name(self, project_name: str = DEFAULT_PROJECT_NAME):
        """Resolve line_id/project by name (no-op if not found)."""
        try:
            from poseidon.backend.database.repositories.project_repository import ProjectRepository
            project = await ProjectRepository.get_by_name(project_name)  # add this helper as suggested
            if project:
                self.line_id = str(project.id)
                self.project_name = project.name
        except Exception:
            pass

    async def load_filter_options(self):
        """Populate static filter dropdowns (once per mount)."""
        try:
            if not self.line_id:
                self.available_defect_types = []
                self.available_cameras = []
                return

            # Cameras
            cameras = await CameraRepository.get_by_project(self.line_id)
            self.available_cameras = sorted({c.name for c in cameras if getattr(c, "name", None)})

            # Defect types (all-time to show complete list; replace with a distinct-aggregation if large)
            classifications = await ScanClassificationRepository.get_by_project_and_date_range(
                self.line_id, None, None
            )
            defects = sorted({cls.det_cls for cls in classifications if getattr(cls, "det_cls", None)})
            self.available_defect_types = defects
        except Exception:
            self.available_defect_types = []
            self.available_cameras = []

    async def load_dashboard_data(self):
        """One fast pass to fetch everything needed for the dashboard."""
        self.loading = True
        self.loading_parts_chart = True
        self.loading_defect_chart = True
        self.loading_defect_histogram_chart = True
        self.loading_weld_chart = True
        self.loading_healthy_vs_defective_chart = True
        self.clear_messages()

        try:
            if not (self.line_id and self.start_date and self.end_date):
                # Clear if incomplete context
                self._clear_all_data()
                return

            scans_task = MetricsRepository.scans_timeseries(self.line_id, self.start_date, self.end_date)
            facets_task = MetricsRepository.classification_facets(
                self.line_id, self.start_date, self.end_date, top_n=DEFECT_HISTOGRAM_LIMIT
            )
            cameras_task = CameraRepository.get_by_project(self.line_id)

            scans, facets, cameras = await asyncio.gather(scans_task, facets_task, cameras_task)


            # --- Timeseries (parts & defect rate) ---
            self.parts_scanned_data = [
                {"date": r["date"], "count": r["count"], "defects": r["defects"]}
                for r in (scans or [])
            ]
            self.defect_rate_data = [
                {"date": r["date"], "defect_rate": r.get("defect_rate", 0.0)}
                for r in (scans or [])
            ]

            # --- Frequent defects / welds / healthy vs defective ---
            self.defect_histogram_data = facets.get("defect_histogram", [])
            self.weld_defect_rate_data = facets.get("weld_defect_rate", [])
            print(f"weld_defect_rate_data: {self.weld_defect_rate_data}")
            # Compute at part-scan level using scans timeseries
            total_defects = sum(r.get("defects", 0) for r in (scans or []))
            total_counts = sum(r.get("count", 0) for r in (scans or []))
            healthy_count = max(0, total_counts - total_defects)
            self.healthy_vs_defective_data = [
                {"status": "Healthy", "count": healthy_count},
                {"status": "Defective", "count": total_defects},
            ]

            # --- Summary metrics ---
            self.total_parts_scanned = sum(r["count"] for r in (scans or []))
            self.total_defects_found = sum(r["defects"] for r in (scans or []))
            self.average_defect_rate = (
                (self.total_defects_found / self.total_parts_scanned) * 100.0
                if self.total_parts_scanned else 0.0
            )
            self.active_cameras = len([c for c in (cameras or []) if getattr(c, "is_active", True)])

        except Exception as e:
            self.set_error(f"Failed to load dashboard data: {e}")
            self._clear_all_data()
        finally:
            self.loading = False
            self.loading_parts_chart = False
            self.loading_defect_chart = False
            self.loading_defect_histogram_chart = False
            self.loading_weld_chart = False
            self.loading_healthy_vs_defective_chart = False

    # -----------------------
    # Helpers
    # -----------------------
    def _clear_all_data(self):
        self.parts_scanned_data = []
        self.defect_rate_data = []
        self.defect_histogram_data = []
        self.weld_defect_rate_data = []
        self.healthy_vs_defective_data = []
        self.total_parts_scanned = 0
        self.total_defects_found = 0
        self.average_defect_rate = 0.0
        self.active_cameras = 0
