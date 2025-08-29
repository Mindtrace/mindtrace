import reflex as rx
from typing import List, Dict, Any, Optional

from poseidon.backend.database.repositories.scan_repository import ScanRepository
from poseidon.backend.cloud.gcs import presign_url


class GridState(rx.State):
    # Table data
    rows: List[Dict[str, Any]] = []
    columns: List[Dict[str, str]] = []
    total: int = 0
    loading: bool = False
    error: str = ""

    current_row_cameras: List[Dict[str, Any]] = []
    expanded_row_id: str = ""

    # Query
    search: str = ""
    result_filter: str = "All"
    sort_by: Optional[str] = "created_at"
    sort_dir: str = "desc"
    page: int = 1
    page_size: int = 20

    # Modal (row-level details)
    modal_open: bool = False
    selected_serial_number: str = ""
    selected_part: str = ""
    selected_created_at: str = ""
    selected_result: str = ""
    selected_operator: str = ""
    selected_model_version: str = ""
    selected_confidence: str = ""

    # Modal (part/image preview extras)
    selected_image_url: str = ""
    selected_part_status: str = ""
    selected_part_classes: List[str] = []
    selected_part_confidence: str = ""
    selected_bbox: Optional[Dict[str, float]] = None
    show_bbox: bool = True  # checkbox in UI

    # ---------- Derived ----------
    @rx.var
    def columns_norm(self) -> list[dict[str, str]]:
        return self.columns or []

    @rx.var
    def columns_css(self) -> str:
        return "2fr 1fr 1fr 1fr"

    @rx.var
    def total_pages(self) -> int:
        return max(1, (self.total + self.page_size - 1) // self.page_size)

    @rx.var
    def pagination_label(self) -> str:
        return f"Page {self.page} of {self.total_pages} — {self.total} results"

    @rx.var
    def prev_disabled(self) -> bool:
        return self.page <= 1 or self.loading

    @rx.var
    def next_disabled(self) -> bool:
        return self.page >= self.total_pages or self.loading

    @rx.var
    def has_rows(self) -> bool:
        return len(self.rows) > 0

    # ---------- Load ----------
    async def load(self):
        self.loading = True
        self.error = ""
        try:
            rows, total, columns = await ScanRepository.search_grid(
                q=self.search or None,
                result=self.result_filter,
                sort_by=self.sort_by or "created_at",
                sort_dir=self.sort_dir,
                page=self.page,
                page_size=self.page_size,
            )
            self.rows = rows
            self.columns = columns
            self.total = total
        except Exception as e:
            self.error = str(e)
            self.rows = []
            self.total = 0
        finally:
            self.loading = False

    # ---------- Helpers ----------
    def get_presigned_url(self, gcs_like_path: str) -> str:
        """
        Return a presigned URL for a GCS path, but pass through if it's already http(s).
        """
        if not gcs_like_path:
            return ""
        if gcs_like_path.startswith(("http://", "https://")):
            return gcs_like_path
        return presign_url(gcs_like_path)

    def _with_presigned_part(self, part: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure a part dict includes a presigned 'image_url'.
        """
        src = (
            part.get("image_url")
            or part.get("full_path")
            or part.get("gcs_path")
            or part.get("path")
            or ""
        )
        return {
            **part,
            "image_url": self.get_presigned_url(str(src)),
        }

    # ---------- Events (return handler reference) ----------
    def set_search(self, v: str):
        self.search = v
        self.page = 1
        return GridState.load

    def set_result_filter(self, v: str):
        self.result_filter = v or "All"
        self.page = 1
        return GridState.load

    def clear_filters(self):
        self.search = ""
        self.result_filter = "All"
        self.page = 1
        return GridState.load

    def set_sort(self, column_id: str):
        if self.sort_by == column_id:
            self.sort_dir = "desc" if self.sort_dir == "asc" else "asc"
        else:
            self.sort_by = column_id
            self.sort_dir = "asc"
        self.page = 1
        return GridState.load

    def next_page(self):
        if self.page < self.total_pages:
            self.page += 1
            return GridState.load

    def prev_page(self):
        if self.page > 1:
            self.page -= 1
            return GridState.load

    def set_page_size(self, n: int):
        self.page_size = max(1, min(200, int(n or 10)))
        self.page = 1
        return GridState.load

    # ---------- Modal helpers ----------
    def open_inspection(self, row: dict[str, Any]):
        """Open the details modal for a scan row (not a specific part)."""
        self.selected_serial_number = str(row.get("serial_number", "-"))
        self.selected_part = str(row.get("part", "-"))
        self.selected_created_at = str(row.get("created_at", "-"))
        self.selected_result = str(row.get("result", "-"))
        self.selected_operator = str(row.get("operator", "-"))
        self.selected_model_version = str(row.get("model_version", "-"))
        self.selected_confidence = str(row.get("confidence", "-"))

        # Clear any part preview fields
        self.selected_image_url = ""
        self.selected_part_status = ""
        self.selected_part_classes = []
        self.selected_part_confidence = ""
        self.selected_bbox = None
        self.show_bbox = True

        self.modal_open = True

    def open_part_preview(self, row: dict[str, Any], part: dict[str, Any]):
        """Populate modal with row + specific part (image-left/details-right use)."""
        # Row-level fields
        self.open_inspection(row)
        part = self._with_presigned_part(part)
        self.selected_image_url = str(part.get("image_url", ""))

        self.selected_part_status = str(part.get("status", ""))
        classes = part.get("classes", []) or []
        self.selected_part_classes = [str(c) for c in classes]

        p_conf = part.get("confidence", None)
        self.selected_part_confidence = (
            f"{float(p_conf):.2f}" if isinstance(p_conf, (int, float)) else "-"
        )

        bbox = part.get("bbox", None)
        self.selected_bbox = bbox if isinstance(bbox, dict) else None
        self.show_bbox = True

        self.modal_open = True

    def set_modal(self, is_open: bool):
        self.modal_open = is_open

    # ---------- Accordion control by ROW (Mongo) id ----------
    def set_expanded_row(self, row_id: str):
        """Set which row is expanded and load its camera data by row id, presigning images."""
        self.expanded_row_id = row_id
        self.current_row_cameras = []

        for row in self.rows:
            if str(row.get("id", "")) == row_id:
                parts_data = row.get("parts", []) or []
                if isinstance(parts_data, list):
                    self.current_row_cameras = [self._with_presigned_part(p) for p in parts_data]
                break

    def handle_accordion_change(self, value: str | list[str]):
        """Handle accordion expansion/collapse."""
        actual_value = value[0] if isinstance(value, list) else (value or "")
        if actual_value and actual_value.startswith("item_"):
            row_id = actual_value.replace("item_", "")
            self.set_expanded_row(row_id)
        else:
            self.expanded_row_id = ""
            self.current_row_cameras = []
