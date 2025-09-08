import math
from typing import List, Dict, Any, Optional

import reflex as rx
from poseidon.backend.database.repositories.data_view_table_repository import TableRepository

# ---- Constants ---------------------------------------------------------------
DEFAULT_SORT_BY = "created_at"
DEFAULT_SORT_DIR = "desc"  # "asc" | "desc"
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 20
MIN_PAGE_SIZE = 1


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
    sort_by: Optional[str] = DEFAULT_SORT_BY
    sort_dir: str = DEFAULT_SORT_DIR
    page: int = DEFAULT_PAGE
    page_size: int = DEFAULT_PAGE_SIZE

    # Modal (row-level details)
    modal_open: bool = False
    selected_serial_number: str = ""
    selected_part: str = ""
    selected_created_at: str = ""
    selected_result: str = ""
    selected_operator: str = ""       # kept for UI compatibility
    selected_model_version: str = ""  # kept for UI compatibility
    selected_confidence: str = ""

    # Modal (part/image preview extras)
    selected_image_url: str = ""
    selected_part_status: str = ""
    selected_part_classes: List[str] = []
    selected_part_confidence: str = ""
    selected_bbox: Optional[Dict[str, float]] = None
    show_bbox: bool = True  # checkbox in UI

    # ---- Internal (not exposed in UI) ----------------------------------------
    _row_index: Dict[str, int] = {}         # Mongo row id -> index into self.rows
    _last_query: Optional[tuple] = None     # Used to skip redundant loads
    _loading_token: int = 0                 # Guards against out-of-order responses

    # ---------- Derived ----------
    @rx.var
    def columns_norm(self) -> List[Dict[str, str]]:
        return self.columns or []

    @rx.var
    def total_pages(self) -> int:
        # Note: total is server-reported (pre client-side result filter)
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

    # ---------- Load ----------
    async def load(self):
        # Normalize query params
        q_tuple = (
            (self.search or "").strip() or None,
            self.result_filter or "All",
            (self.sort_by or DEFAULT_SORT_BY),
            (self.sort_dir or DEFAULT_SORT_DIR),
            int(self.page),
            int(self.page_size),
        )

        # Dedupe only if we actually have rows and nothing changed
        if self._last_query == q_tuple and self.rows:
            # debug: useful if you’re not seeing backend logs
            print("[GridState.load] skipped (deduped)", flush=True)
            return

        # Prevent concurrent loads; handle out-of-order completions
        self._loading_token += 1
        token = self._loading_token
        self.loading = True
        self.error = ""
        print(f"[GridState.load] start q={q_tuple}", flush=True)

        try:
            rows, total, columns = await ScanRepository.search_grid(
                q=q_tuple[0],
                result=q_tuple[1],   # repo may ignore; we filter client-side below
                sort_by=q_tuple[2],  # server sorts native fields (created_at, serial_number)
                sort_dir=q_tuple[3],
                page=q_tuple[4],
                page_size=q_tuple[5],
            )

            # If another load started after us, drop these results
            if token != self._loading_token:
                print("[GridState.load] stale result dropped", flush=True)
                return

            # --- client-side filter by result (computed on the row) ---
            filtered_rows = rows or []
            if self.result_filter and self.result_filter != "All":
                wanted = (self.result_filter or "").strip().lower()
                before = len(filtered_rows)
                filtered_rows = [r for r in filtered_rows if str(r.get("result", "")).lower() == wanted]
                print(f"[GridState.load] client result filter={self.result_filter} kept {len(filtered_rows)}/{before}", flush=True)

            # --- client-side sort for computed fields only ---
            # Server sorts DB fields already; for 'part' or 'result' we sort here.
            if self.sort_by in ("part", "result"):
                reverse = (self.sort_dir == "desc")
                key_id = self.sort_by
                filtered_rows.sort(
                    key=lambda r: str(r.get(key_id, "") or "").lower(),
                    reverse=reverse,
                )
                print(f"[GridState.load] client sort by {key_id} {self.sort_dir}", flush=True)

            # Assign to state
            self.rows = filtered_rows
            self.total = int(total or 0)      # server total (pre client filter)
            self.columns = columns or []
            self._last_query = q_tuple

            # Rebuild id->index map once per load
            self._row_index = {str(r.get("id", "")): i for i, r in enumerate(self.rows)}

            # If the expanded row disappeared, tidy up
            if self.expanded_row_id and self.expanded_row_id not in self._row_index:
                self.expanded_row_id = ""
                self.current_row_cameras = []

            print(f"[GridState.load] done rows={len(self.rows)} total={self.total}", flush=True)

        except Exception as e:
            if token == self._loading_token:
                self.error = str(e)
                self.rows = []
                self.total = 0
                self.columns = []
                self._row_index = {}
                self._last_query = None
            print(f"[GridState.load] ERROR: {e}", flush=True)
        finally:
            if token == self._loading_token:
                self.loading = False

    def _clamp_page_size(self, n: int) -> int:
        try:
            n = int(n)
        except Exception:
            n = DEFAULT_PAGE_SIZE
        return max(MIN_PAGE_SIZE, min(MAX_PAGE_SIZE, n))

    # ---------- Events (return handler reference) ----------
    def set_search(self, v: str):
        v = (v or "").strip()
        if v == self.search and self.page == 1:
            return  # no-op
        self.search = v
        self.page = 1
        self._last_query = None  # force re-load
        return GridState.load

    def set_result_filter(self, v: str):
        v = (v or "All").strip() or "All"
        if v == self.result_filter and self.page == 1:
            return
        self.result_filter = v
        self.page = 1
        self._last_query = None
        return GridState.load

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
            self._last_query = None
            return GridState.load

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
        self._last_query = None
        return GridState.load

    def next_page(self):
        if self.page < self.total_pages:
            self.page += 1
            self._last_query = None
            return GridState.load

    def prev_page(self):
        if self.page > 1:
            self.page -= 1
            self._last_query = None
            return GridState.load

    def set_page_size(self, n: int):
        new_size = self._clamp_page_size(n)
        if new_size == self.page_size and self.page == 1:
            return
        self.page_size = new_size
        self.page = 1
        self._last_query = None
        return GridState.load

    # ---------- Modal helpers ----------
    def _reset_part_preview(self):
        self.selected_image_url = ""
        self.selected_part_status = ""
        self.selected_part_classes = []
        self.selected_part_confidence = ""
        self.selected_bbox = None
        self.show_bbox = True

    def open_inspection(self, row: Dict[str, Any]):
        """Open the details modal for a scan row (not a specific part)."""
        self.selected_serial_number = str(row.get("serial_number", "-"))
        self.selected_part = str(row.get("part", "-"))
        self.selected_created_at = str(row.get("created_at", "-"))
        self.selected_result = str(row.get("result", "-"))
        self.selected_confidence = str(row.get("confidence", "-"))
        # compatibility placeholders
        self.selected_operator = str(row.get("operator", "-"))
        self.selected_model_version = str(row.get("model_version", "-"))
        self._reset_part_preview()
        self.modal_open = True

    # Repo already returns presigned image_url; keep for backwards compat
    def _with_presigned_part(self, part: Dict[str, Any]) -> Dict[str, Any]:
        return part or {}

    def open_part_preview(self, row: Dict[str, Any], part: Dict[str, Any]):
        """Populate modal with row + specific part (image-left / details-right use)."""
        self.open_inspection(row)

        part = self._with_presigned_part(part or {})
        self.selected_image_url = str(part.get("image_url", ""))

        self.selected_part_status = str(part.get("status", ""))
        classes = part.get("classes") or []
        self.selected_part_classes = [str(c) for c in classes] if isinstance(classes, list) else []

        p_conf = part.get("confidence", None)
        self.selected_part_confidence = (f"{float(p_conf):.2f}" if isinstance(p_conf, (int, float)) else "-")

        bbox = part.get("bbox", None)
        self.selected_bbox = bbox if isinstance(bbox, dict) else None
        self.show_bbox = True  # default checked

    def set_modal(self, is_open: bool):
        self.modal_open = bool(is_open)

    # ---------- Accordion control by ROW (Mongo) id ----------
    def _load_row_parts(self, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        parts_data = row.get("parts") or []
        if not isinstance(parts_data, list):
            return []
        # No presign needed; already presigned by repo
        return [self._with_presigned_part(p) for p in parts_data]

    def set_expanded_row(self, row_id: str):
        """Set which row is expanded and load its camera data by row id."""
        row_id = str(row_id or "")
        self.expanded_row_id = row_id
        self.current_row_cameras = []

        if not row_id:
            return

        idx = self._row_index.get(row_id, -1)
        if idx < 0 or idx >= len(self.rows):
            return

        row = self.rows[idx]
        self.current_row_cameras = self._load_row_parts(row)

    def handle_accordion_change(self, value: str | List[str]):
        """Handle accordion expansion/collapse."""
        actual_value = value[0] if isinstance(value, list) and value else (value or "")
        if isinstance(actual_value, str) and actual_value.startswith("item_"):
            self.set_expanded_row(actual_value.replace("item_", "", 1))
        else:
            self.expanded_row_id = ""
            self.current_row_cameras = []
