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

DEFECT_HISTOGRAM_LIMIT = 10


class LineInsightsState(BaseFilterState):
    """State management for Line Insights dashboard."""

    # Global time filtering
    date_range: str = "last_7_days"  # last_1_day, last_7_days, last_30_days, last_90_days, custom
    start_date: Optional[datetime] = None  # timezone-aware UTC
    end_date: Optional[datetime] = None  # timezone-aware UTC (exclusive upper bound)

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

    loading_charts: bool = False

    @rx.event
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
        return type(self).load_dashboard_data

    @rx.event
    async def on_mount(self):
        """Initialize filters and data for current line scope."""
        if not self.start_date:
            now = datetime.now(timezone.utc)
            self.date_range = "last_7_days"
            self.start_date = now - timedelta(days=7)
            self.end_date = now
        return type(self).load_dashboard_data

    @rx.event
    async def load_dashboard_data(self):
        """One fast pass to fetch everything needed for the dashboard."""
        self.loading_charts = True
        self.clear_messages()
        yield

        try:
            if not (self.line_id and self.start_date and self.end_date):
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
                {"date": r["date"], "count": r["count"], "defects": r["defects"]} for r in (scans or [])
            ]
            self.defect_rate_data = [
                {"date": r["date"], "defect_rate": r.get("defect_rate", 0.0)} for r in (scans or [])
            ]

            # --- Frequent defects / welds / healthy vs defective ---
            self.defect_histogram_data = facets.get("defect_histogram", [])
            self.weld_defect_rate_data = facets.get("weld_defect_rate", [])

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
                (self.total_defects_found / self.total_parts_scanned) * 100.0 if self.total_parts_scanned else 0.0
            )
            self.active_cameras = len([c for c in (cameras or []) if getattr(c, "is_active", True)])

        except Exception as e:
            self.set_error(f"Failed to load dashboard data: {e}")
            self.loading_charts = False
            self._clear_all_data()
        finally:
            self.loading_charts = False
            yield


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
