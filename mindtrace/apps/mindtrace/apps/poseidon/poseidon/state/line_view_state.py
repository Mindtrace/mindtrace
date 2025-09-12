import math
from typing import List, Dict, Any, Optional

import reflex as rx
from poseidon.backend.database.repositories.data_view_table_repository import TableRepository

# ---- Constants ---------------------------------------------------------------
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 20
MIN_PAGE_SIZE = 1


class LineViewState(rx.State):
    # -------------------------- Table data -----------------------------------
    rows: List[Dict[str, Any]] = []
    columns: List[Dict[str, str]] = []
    total: int = 0
    loading: bool = False
    error: str = ""

    # Expanded row chips
    current_row_cameras: List[Dict[str, Any]] = []
    expanded_row_id: str = ""
    parts_loading: bool = False

    # -------------------------- Query params ---------------------------------
    search: str = ""
    result_filter: str = "All"
    sort_by: str = "created_at"
    sort_dir: str = "desc"
    page: int = DEFAULT_PAGE
    page_size: int = DEFAULT_PAGE_SIZE

    # -------------------------- Modal (details) ------------------------------
    modal_open: bool = False
    selected_serial_number: str = ""
    selected_part: str = ""
    selected_result: str = ""
    selected_image_url: str = ""
    selected_part_status: str = ""
    show_bbox: bool = True

    # -------------------------- Internal ------------------------------------
    _loading_token: int = 0  # prevents stale writes

    # -------------------------- Derived --------------------------------------
    @rx.var
    def total_pages(self) -> int:
        return max(1, math.ceil(self.total / max(MIN_PAGE_SIZE, self.page_size)))

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
        return bool(self.rows)

    # -------------------------- Lifecycle ------------------------------------
    @rx.event
    def on_mount(self):
        return LineViewState.load

    # ------------------------ Detail view loader -----------------------------
    async def load_detail_view(self):
        """Fetch chips for the currently expanded row."""
        rid = (self.expanded_row_id or "").strip()
        if not rid:
            self.current_row_cameras = []
            return
        self.parts_loading = True
        try:
            parts = await TableRepository.fetch_row_parts(rid)
        except Exception as e:
            print(f"[LineViewState.load_detail_view] ERROR for {rid}: {e}", flush=True)
            parts = []
        finally:
            # Only apply if still on the same row
            if self.expanded_row_id == rid:
                self.current_row_cameras = parts
                self.parts_loading = False

    # ----------------------------- Grid loader -------------------------------
    async def load(self):
        self._loading_token += 1
        token = self._loading_token
        self.loading = True
        self.error = ""
        try:
            rows, total, columns = await TableRepository.search_grid(
                q=(self.search or None),
                result=(self.result_filter or "All"),
                sort_by=(self.sort_by or "created_at"),
                sort_dir=(self.sort_dir or "desc"),
                page=int(self.page),
                page_size=int(self.page_size),
                line_id=(self.line_id or None),
            )
            if token != self._loading_token:
                # stale result; another load started after this one
                return

            self.rows = rows or []
            self.total = int(total or 0)
            self.columns = columns or []

            # If we changed pages/filters and the expanded row is gone, collapse it
            if self.expanded_row_id and not any(r.get("id") == self.expanded_row_id for r in self.rows):
                self.expanded_row_id = ""
                self.current_row_cameras = []
        except Exception as e:
            if token == self._loading_token:
                self.error = str(e)
                self.rows = []
                self.total = 0
                self.columns = []
            print(f"[LineViewState.load] ERROR: {e}", flush=True)
        finally:
            if token == self._loading_token:
                self.loading = False

    # ------------------------------ Helpers ----------------------------------
    def _clamp_page_size(self, n: int) -> int:
        try:
            n = int(n)
        except Exception:
            n = DEFAULT_PAGE_SIZE
        return max(MIN_PAGE_SIZE, min(MAX_PAGE_SIZE, n))

    def _reset_part_preview(self):
        self.selected_image_url = ""
        self.selected_part_status = ""
        self.show_bbox = True

    # ------------------------------- Events ----------------------------------
    def set_line_id(self, v: Optional[str]):
        # changing line should refetch immediately
        if v == self.line_id and self.page == 1:
            return
        self.line_id = v or None
        self.page = 1
        return LineViewState.load

    def set_search(self, v: str):
        v = (v or "").strip()
        if v == self.search and self.page == 1:
            return
        self.search = v
        self.page = 1
        return LineViewState.load

    def set_result_filter(self, v: str):
        v = (v or "All").strip() or "All"
        if v == self.result_filter and self.page == 1:
            return
        self.result_filter = v
        self.page = 1
        return LineViewState.load

    def clear_filters(self):
        changed = False
        if self.search:
            self.search = ""
            changed = True
        if self.result_filter != "All":
            self.result_filter = "All"
            changed = True
        if self.page != 1:
            self.page = 1
            changed = True
        if changed:
            return LineViewState.load

    def set_sort(self, column_id: str):
        column_id = (column_id or "").strip()
        if not column_id:
            return
        if self.sort_by == column_id:
            self.sort_dir = "desc" if self.sort_dir == "asc" else "asc"
        else:
            self.sort_by = column_id
            self.sort_dir = "asc"
        self.page = 1
        return LineViewState.load

    def next_page(self):
        if self.page < self.total_pages:
            self.page += 1
            return LineViewState.load

    def prev_page(self):
        if self.page > 1:
            self.page -= 1
            return LineViewState.load

    def set_page_size(self, n: int):
        new_size = self._clamp_page_size(n)
        if new_size == self.page_size and self.page == 1:
            return
        self.page_size = new_size
        self.page = 1
        return LineViewState.load

    # --------------------------- Modal actions --------------------------------
    def open_inspection(self, row: Dict[str, Any]):
        self.selected_serial_number = str(row.get("serial_number", "-"))
        self.selected_part = str(row.get("part", "-"))
        self.selected_result = str(row.get("result", "-"))
        self._reset_part_preview()
        self.modal_open = True

    def open_part_preview(self, row: Dict[str, Any], part: Dict[str, Any]):
        # open modal and populate preview bits
        self.open_inspection(row)
        part = part or {}
        self.selected_image_url = str(part.get("image_url", ""))
        self.selected_part_status = str(part.get("status", ""))
        self.show_bbox = True

    def set_modal(self, is_open: bool):
        self.modal_open = bool(is_open)

    # --------------------- Accordion control by row id ------------------------
    def toggle_row(self, row_id: str):
        row_id = str(row_id or "")
        if self.expanded_row_id == row_id:
            # collapse
            self.expanded_row_id = ""
            self.current_row_cameras = []
            return
        # expand and lazy-load
        self.expanded_row_id = row_id
        self.current_row_cameras = []
        return LineViewState.load_detail_view
