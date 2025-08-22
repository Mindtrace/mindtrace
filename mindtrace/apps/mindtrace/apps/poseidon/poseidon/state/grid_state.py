import reflex as rx
from typing import List, Dict, Any, Optional


class GridState(rx.State):
    """Generic, reusable state for filterable/sortable/paginated tables."""

    # --- static table data ---
    rows: List[Dict[str, Any]] = [
        {"timestamp": "15 JAN, 02:00 PM", "part_number": "P-A001-847", "defect_type": "Surface", "ai_labels": "Surface", "operator": "Normal Wear", "confidence": "94.5%", "image": "View", "outcome": "Override"},
        {"timestamp": "15 JAN, 02:00 PM", "part_number": "P-A001-847", "defect_type": "Surface", "ai_labels": "Surface", "operator": "Normal Wear", "confidence": "94.5%", "image": "View", "outcome": "Override"},
        {"timestamp": "15 JAN, 02:00 PM", "part_number": "P-A001-847", "defect_type": "Surface", "ai_labels": "Surface", "operator": "Normal Wear", "confidence": "94.5%", "image": "View", "outcome": "Override"},
        {"timestamp": "15 JAN, 02:00 PM", "part_number": "P-A001-847", "defect_type": "Surface", "ai_labels": "Surface", "operator": "Normal Wear", "confidence": "94.5%", "image": "View", "outcome": "Override"},
        {"timestamp": "15 JAN, 02:00 PM", "part_number": "P-A001-847", "defect_type": "Surface", "ai_labels": "Surface", "operator": "Normal Wear", "confidence": "94.5%", "image": "View", "outcome": "Override"},
        {"timestamp": "15 JAN, 02:00 PM", "part_number": "P-A001-847", "defect_type": "Surface", "ai_labels": "Surface", "operator": "Normal Wear", "confidence": "94.5%", "image": "View", "outcome": "Override"},
        {"timestamp": "25 JAN, 01:31 AM", "part_number": "P-A001-846", "defect_type": "Weld", "ai_labels": "Pass", "operator": "Weld Defect", "confidence": "87.3%", "image": "View", "outcome": "Catch"},
        {"timestamp": "25 JAN, 01:31 AM", "part_number": "P-A001-846", "defect_type": "Weld", "ai_labels": "Pass", "operator": "Weld Defect", "confidence": "87.3%", "image": "View", "outcome": "Catch"},
        {"timestamp": "25 JAN, 01:31 AM", "part_number": "P-A001-846", "defect_type": "Weld", "ai_labels": "Pass", "operator": "Weld Defect", "confidence": "87.3%", "image": "View", "outcome": "Catch"},
        {"timestamp": "25 JAN, 01:31 AM", "part_number": "P-A001-846", "defect_type": "Weld", "ai_labels": "Pass", "operator": "Weld Defect", "confidence": "87.3%", "image": "View", "outcome": "Catch"},
        {"timestamp": "25 JAN, 01:31 AM", "part_number": "P-A001-846", "defect_type": "Weld", "ai_labels": "Pass", "operator": "Weld Defect", "confidence": "87.3%", "image": "View", "outcome": "Catch"},
        {"timestamp": "25 JAN, 01:31 AM", "part_number": "P-A001-846", "defect_type": "Weld", "ai_labels": "Pass", "operator": "Weld Defect", "confidence": "87.3%", "image": "View", "outcome": "Catch"},
        {"timestamp": "25 JAN, 01:31 AM", "part_number": "P-A001-846", "defect_type": "Weld", "ai_labels": "Pass", "operator": "Weld Defect", "confidence": "87.3%", "image": "View", "outcome": "Catch"},
        {"timestamp": "25 JAN, 01:31 AM", "part_number": "P-A001-846", "defect_type": "Weld", "ai_labels": "Pass", "operator": "Weld Defect", "confidence": "87.3%", "image": "View", "outcome": "Catch"},
        {"timestamp": "25 JAN, 01:31 AM", "part_number": "P-A001-846", "defect_type": "Weld", "ai_labels": "Pass", "operator": "Weld Defect", "confidence": "87.3%", "image": "View", "outcome": "Catch"},
        {"timestamp": "25 JAN, 01:31 AM", "part_number": "P-A001-846", "defect_type": "Weld", "ai_labels": "Pass", "operator": "Weld Defect", "confidence": "87.3%", "image": "View", "outcome": "Catch"},
        {"timestamp": "25 JAN, 01:31 AM", "part_number": "P-A001-846", "defect_type": "Weld", "ai_labels": "Pass", "operator": "Weld Defect", "confidence": "87.3%", "image": "View", "outcome": "Catch"},
        {"timestamp": "25 JAN, 01:31 AM", "part_number": "P-A001-846", "defect_type": "Weld", "ai_labels": "Pass", "operator": "Weld Defect", "confidence": "87.3%", "image": "View", "outcome": "Catch"},
        {"timestamp": "25 JAN, 01:31 AM", "part_number": "P-A001-846", "defect_type": "Weld", "ai_labels": "Pass", "operator": "Weld Defect", "confidence": "87.3%", "image": "View", "outcome": "Catch"},
        {"timestamp": "07 FEB, 12:34 PM", "part_number": "P-A001-845", "defect_type": "Missing", "ai_labels": "Missing", "operator": "-", "confidence": "96.8%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "07 FEB, 12:34 PM", "part_number": "P-A001-845", "defect_type": "Missing", "ai_labels": "Missing", "operator": "-", "confidence": "96.8%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "07 FEB, 12:34 PM", "part_number": "P-A001-845", "defect_type": "Missing", "ai_labels": "Missing", "operator": "-", "confidence": "96.8%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "07 FEB, 12:34 PM", "part_number": "P-A001-845", "defect_type": "Missing", "ai_labels": "Missing", "operator": "-", "confidence": "96.8%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "07 FEB, 12:34 PM", "part_number": "P-A001-845", "defect_type": "Missing", "ai_labels": "Missing", "operator": "-", "confidence": "96.8%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "07 FEB, 12:34 PM", "part_number": "P-A001-845", "defect_type": "Missing", "ai_labels": "Missing", "operator": "-", "confidence": "96.8%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "07 FEB, 12:34 PM", "part_number": "P-A001-845", "defect_type": "Missing", "ai_labels": "Missing", "operator": "-", "confidence": "96.8%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "29 APR, 06:53 AM", "part_number": "P-A001-842", "defect_type": "Alignment", "ai_labels": "Alignment", "operator": "Pass", "confidence": "78.5%", "image": "View", "outcome": "Override"},
        {"timestamp": "29 APR, 06:53 AM", "part_number": "P-A001-842", "defect_type": "Alignment", "ai_labels": "Alignment", "operator": "Pass", "confidence": "78.5%", "image": "View", "outcome": "Override"},
        {"timestamp": "29 APR, 06:53 AM", "part_number": "P-A001-842", "defect_type": "Alignment", "ai_labels": "Alignment", "operator": "Pass", "confidence": "78.5%", "image": "View", "outcome": "Override"},
        {"timestamp": "29 APR, 06:53 AM", "part_number": "P-A001-842", "defect_type": "Alignment", "ai_labels": "Alignment", "operator": "Pass", "confidence": "78.5%", "image": "View", "outcome": "Override"},
        {"timestamp": "29 APR, 06:53 AM", "part_number": "P-A001-842", "defect_type": "Alignment", "ai_labels": "Alignment", "operator": "Pass", "confidence": "78.5%", "image": "View", "outcome": "Override"},
        {"timestamp": "29 APR, 06:53 AM", "part_number": "P-A001-842", "defect_type": "Alignment", "ai_labels": "Alignment", "operator": "Pass", "confidence": "78.5%", "image": "View", "outcome": "Override"},
        {"timestamp": "18 JUN, 04:35 PM", "part_number": "P-A001-840", "defect_type": "None", "ai_labels": "Pass", "operator": "-", "confidence": "92.1%", "image": "View", "outcome": "Pass"},
        {"timestamp": "18 JUN, 04:35 PM", "part_number": "P-A001-840", "defect_type": "None", "ai_labels": "Pass", "operator": "-", "confidence": "92.1%", "image": "View", "outcome": "Pass"},
        {"timestamp": "18 JUN, 04:35 PM", "part_number": "P-A001-840", "defect_type": "None", "ai_labels": "Pass", "operator": "-", "confidence": "92.1%", "image": "View", "outcome": "Pass"},
        {"timestamp": "18 JUN, 04:35 PM", "part_number": "P-A001-840", "defect_type": "None", "ai_labels": "Pass", "operator": "-", "confidence": "92.1%", "image": "View", "outcome": "Pass"},
        {"timestamp": "18 JUN, 04:35 PM", "part_number": "P-A001-840", "defect_type": "None", "ai_labels": "Pass", "operator": "-", "confidence": "92.1%", "image": "View", "outcome": "Pass"},
        {"timestamp": "18 JUN, 04:35 PM", "part_number": "P-A001-840", "defect_type": "None", "ai_labels": "Pass", "operator": "-", "confidence": "92.1%", "image": "View", "outcome": "Pass"},
        {"timestamp": "18 JUN, 04:35 PM", "part_number": "P-A001-840", "defect_type": "None", "ai_labels": "Pass", "operator": "-", "confidence": "92.1%", "image": "View", "outcome": "Pass"},
        {"timestamp": "18 JUN, 04:35 PM", "part_number": "P-A001-840", "defect_type": "None", "ai_labels": "Pass", "operator": "-", "confidence": "92.1%", "image": "View", "outcome": "Pass"},
        {"timestamp": "18 JUN, 04:35 PM", "part_number": "P-A001-840", "defect_type": "None", "ai_labels": "Pass", "operator": "-", "confidence": "92.1%", "image": "View", "outcome": "Pass"},
        {"timestamp": "20 JUL, 06:22 PM", "part_number": "P-A001-839", "defect_type": "Surface", "ai_labels": "Surface", "operator": "-", "confidence": "83.4%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "20 JUL, 06:22 PM", "part_number": "P-A001-839", "defect_type": "Surface", "ai_labels": "Surface", "operator": "-", "confidence": "83.4%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "20 JUL, 06:22 PM", "part_number": "P-A001-839", "defect_type": "Surface", "ai_labels": "Surface", "operator": "-", "confidence": "83.4%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "20 JUL, 06:22 PM", "part_number": "P-A001-839", "defect_type": "Surface", "ai_labels": "Surface", "operator": "-", "confidence": "83.4%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "20 JUL, 06:22 PM", "part_number": "P-A001-839", "defect_type": "Surface", "ai_labels": "Surface", "operator": "-", "confidence": "83.4%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "20 JUL, 06:22 PM", "part_number": "P-A001-839", "defect_type": "Surface", "ai_labels": "Surface", "operator": "-", "confidence": "83.4%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "20 JUL, 06:22 PM", "part_number": "P-A001-839", "defect_type": "Surface", "ai_labels": "Surface", "operator": "-", "confidence": "83.4%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "20 JUL, 06:22 PM", "part_number": "P-A001-839", "defect_type": "Surface", "ai_labels": "Surface", "operator": "-", "confidence": "83.4%", "image": "View", "outcome": "Confirmed"},
        {"timestamp": "20 JUL, 06:22 PM", "part_number": "P-A001-839", "defect_type": "Surface", "ai_labels": "Surface", "operator": "-", "confidence": "83.4%", "image": "View", "outcome": "Confirmed"},
    ]

    columns: List[Dict[str, Any]] = [
        {"id": "timestamp", "header": "Timestamp"},
        {"id": "part_number", "header": "Part Number"},
        {"id": "defect_type", "header": "Defect Type"},
        {"id": "ai_labels", "header": "AI Labels"},
        {"id": "operator", "header": "Operator"},
        {"id": "confidence", "header": "Confidence"},
        {"id": "image", "header": "Image"},
        {"id": "outcome", "header": "Outcome"},
    ]

    filter_config: List[Dict[str, Any]] = [
        {"id": "defect_type", "label": "Defect Type"},
        {"id": "ai_labels", "label": "AI Labels"},
        {"id": "operator", "label": "Operator"},
        {"id": "outcome", "label": "Outcome"},
    ]
    filters: Dict[str, str] = {}

    search: str = ""
    sort_by: Optional[str] = None
    sort_dir: str = "asc"
    page: int = 1
    page_size: int = 10

    # ---- modal state ----
    modal_open: bool = False

    selected_image_url: str = ""
    selected_ai_labels: str = ""
    selected_operator_label: str = ""
    selected_station: str = ""
    selected_operator: str = ""
    selected_model_version: str = ""
    selected_confidence: str = ""
    selected_part_number: str = ""
    selected_defect_desc: str = ""
    selected_ai_time_ago: str = ""
    selected_op_time_ago: str = ""
    selected_log_time_ago: str = ""
    selected_comment: str = ""
    selected_comment_time_ago: str = ""

    # --- derived ---
    @rx.var
    def available_filter_options(self) -> dict[str, list[str]]:
        options: Dict[str, List[str]] = {}
        for f in self.filter_config:
            fid = f["id"]
            vals = f.get("options") or [str(r.get(fid, "")) for r in self.rows]
            options[fid] = ["All"] + sorted({v for v in vals if v})
        return options

    @rx.var
    def filter_config_norm(self) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for f in self.filter_config:
            fid = str(f["id"])
            label = str(f.get("label") or fid.title())
            out.append({"id": fid, "label": label})
        return out

    @rx.var
    def columns_norm(self) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for c in self.columns:
            cid = str(c["id"])
            header = str(c.get("header") or cid.title())
            out.append({"id": cid, "header": header})
        return out

    @rx.var
    def filtered_rows(self) -> list[dict[str, Any]]:
        data = self.rows
        for k, v in self.filters.items():
            if v and v != "All":
                data = [r for r in data if str(r.get(k, "")) == str(v)]
        s = self.search.strip().lower()
        if s:
            keys = [c["id"] for c in self.columns]
            data = [r for r in data if any(s in str(r.get(k, "")).lower() for k in keys)]
        return data

    @rx.var
    def filtered_sorted_rows(self) -> list[dict[str, Any]]:
        data = list(self.filtered_rows)
        if self.sort_by:
            reverse = self.sort_dir == "desc"
            data.sort(key=lambda r: str(r.get(self.sort_by, "")).lower(), reverse=reverse)
        return data

    @rx.var
    def visible_rows_list(self) -> list[dict[str, Any]]:
        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        return self.filtered_sorted_rows[start:end]

    @rx.var
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 1
        return max(1, (len(self.filtered_sorted_rows) + self.page_size - 1) // self.page_size)

    @rx.var
    def columns_css(self) -> str:
        return f"repeat({len(self.columns)}, minmax(0, 1fr))"

    @rx.var
    def result_count(self) -> int:
        return len(self.filtered_sorted_rows)

    @rx.var
    def pagination_label(self) -> str:
        return f"Page {self.page} of {self.total_pages} — {self.result_count} results"

    @rx.var
    def prev_disabled(self) -> bool:
        return self.page <= 1

    @rx.var
    def next_disabled(self) -> bool:
        return self.page >= self.total_pages

    @rx.var
    def has_rows(self) -> bool:
        return len(self.visible_rows_list) > 0
    
    @rx.var
    def filtered_sorted_rows(self) -> list[dict[str, Any]]:
        data = list(self.filtered_rows)

        for r in data:
            imgs = r.get("images")
            if not isinstance(imgs, list):
                r["images"] = []
            r["images_count"] = len(r["images"])

        if self.sort_by:
            reverse = self.sort_dir == "desc"
            data.sort(key=lambda r: str(r.get(self.sort_by, "")).lower(), reverse=reverse)
        return data

    # --- events ---
    def set_filter(self, fid: str, value: str):
        self.filters[fid] = value
        self.page = 1

    def clear_filters(self):
        self.filters = {f["id"]: "All" for f in self.filter_config}
        self.search = ""
        self.page = 1

    def set_search(self, v: str):
        self.search = v
        self.page = 1

    def set_sort(self, column_id: str):
        if self.sort_by == column_id:
            self.sort_dir = "desc" if self.sort_dir == "asc" else "asc"
        else:
            self.sort_by = column_id
            self.sort_dir = "asc"
        self.page = 1

    def next_page(self):
        if self.page < self.total_pages:
            self.page += 1

    def prev_page(self):
        if self.page > 1:
            self.page -= 1

    def open_inspection(self, row: dict[str, Any]):
        self.selected_image_url = str(row.get("image_url", ""))
        self.selected_ai_labels = str(row.get("ai_labels", "-"))
        self.selected_operator_label = str(row.get("operator_label", "-"))
        self.selected_station = str(row.get("station", "-"))
        self.selected_operator = str(row.get("operator", "-"))
        self.selected_model_version = str(row.get("model_version", "-"))
        self.selected_confidence = str(row.get("confidence", "-"))
        self.selected_part_number = str(row.get("part_number", "-"))
        self.selected_defect_desc = str(row.get("defect_desc", "-"))
        self.selected_ai_time_ago = str(row.get("ai_time_ago", "-"))
        self.selected_op_time_ago = str(row.get("op_time_ago", "-"))
        self.selected_log_time_ago = str(row.get("log_time_ago", "-"))
        self.selected_comment = str(row.get("comment", "-"))
        self.selected_comment_time_ago = str(row.get("comment_time_ago", "-"))
        self.modal_open = True

    def set_modal(self, is_open: bool):
        self.modal_open = is_open
