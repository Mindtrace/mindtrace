import reflex as rx
from typing import List, Dict, Any, Optional
from poseidon.backend.database.repositories.scan_repository import ScanRepository

class GridState(rx.State):
    rows: List[Dict[str, Any]] = []
    columns: List[Dict[str, str]] = []
    total: int = 0
    loading: bool = False
    error: str = ""

    # Query
    search: str = ""
    result_filter: str = "All"
    sort_by: Optional[str] = "created_at"  # "serial_number" | "part" | "created_at" | "result"
    sort_dir: str = "desc"
    page: int = 1
    page_size: int = 10

    # Modal
    modal_open: bool = False
    selected_serial_number: str = ""
    selected_part: str = ""
    selected_created_at: str = ""
    selected_result: str = ""

    @rx.var
    def columns_norm(self) -> list[dict[str, str]]:
        return self.columns or []

    @rx.var
    def columns_css(self) -> str:
        # Serial number gets more space
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

    # -------- DB load (async) --------
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

    # -------- Events (return handler reference, not coroutine) --------
    def set_search(self, v: str):
        self.search = v
        self.page = 1
        return self.load

    def set_result_filter(self, v: str):
        self.result_filter = (v or "All")
        self.page = 1
        return self.load

    def clear_filters(self):
        self.search = ""
        self.result_filter = "All"
        self.page = 1
        return self.load

    def set_sort(self, column_id: str):
        if self.sort_by == column_id:
            self.sort_dir = "desc" if self.sort_dir == "asc" else "asc"
        else:
            self.sort_by = column_id
            self.sort_dir = "asc"
        self.page = 1
        return self.load

    def next_page(self):
        if self.page < self.total_pages:
            self.page += 1
            return self.load

    def prev_page(self):
        if self.page > 1:
            self.page -= 1
            return self.load

    def set_page_size(self, n: int):
        self.page_size = max(1, min(200, int(n or 10)))
        self.page = 1
        return self.load

    # -------- Modal helpers --------
    def open_inspection(self, row: dict[str, Any]):
        self.selected_serial_number = str(row.get("serial_number", "-"))
        self.selected_part = str(row.get("part", "-"))
        self.selected_created_at = str(row.get("created_at", "-"))
        self.selected_result = str(row.get("result", "-"))
        self.modal_open = True

    def set_modal(self, is_open: bool):
        self.modal_open = is_open
