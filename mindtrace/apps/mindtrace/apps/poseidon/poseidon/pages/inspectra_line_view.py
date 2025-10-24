import reflex as rx
from typing import List, Dict, Union, Optional
from datetime import datetime, timedelta
import random

# ──────────────────────────────────────────────────────────────
# Dummy constants
# ──────────────────────────────────────────────────────────────
DEFECT_TYPES = [
    "Off Location Weld", "Weld Cracks", "Burn Through", "Porosity or Pits",
    "Melt Back or Notching", "Lack of Fusion (Cold Weld)", "Blow Hole",
    "Missing Weld", "Excessive Gap", "Undercut", "Crater", "Short Weld",
    "Skip or Discontinuation", "Overlap", "Unstable Weld", "Wire Stick",
    "Spatter", "Melt Through",
]

WELD_LOCATIONS = [
    "IB_WA1","IB_WA2","IB_WA3","IB_WA4","IB_WA5","IB_WA6","IB_WA7","IB_WA8","IB_WA9","IB_WA10","IB_WA11",
    "IB_Z_1","IB_Z_2","IB_Z_3","IB_Z_4","IB_Z_5","IB_Z_6","IB_Z_2_2","IB_Z_7_1","IB_Z_7_2",
    "OB_WA1","OB_WA2","OB_WA3","OB_WA4","OB_WA5","OB_WA6","OB_WA7","OB_WA8","OB_WA9","OB_WA10","OB_WA11",
    "OB_Z_1","OB_Z_2","OB_Z_3","OB_Z_4","OB_Z_5","OB_Z_6","OB_Z_7","OB_Z_8_1","OB_Z_8_2","OB_Z_9","OB_Z_10_1","OB_Z_10_2"
]

def generate_dummy_rows() -> List[Dict[str, Union[str, int]]]:
    """Fixed dummy inspection data (healthy + defective + mixed welds)."""
    def weld(locations, defects=None):
        """Return weld list with some defects."""
        defects = defects or {}
        return [
            {"location": loc, "status": defects.get(loc, "Healthy")}
            for loc in locations
        ]

    inner = [loc for loc in WELD_LOCATIONS if loc.startswith("IB_")]
    outer = [loc for loc in WELD_LOCATIONS if loc.startswith("OB_")]

    rows = [
        {
            "serial": "10474800000000001_10474900000000001",
            "part": "Part 1",
            "created_at": "2025-10-23 09:00:00",
            "result": "Healthy",
            "defect_type": "Healthy",
            "weld_location": "IB_WA1",
            "welds": weld(inner + outer),
        },
        {
            "serial": "10474800000000002_10474900000000002",
            "part": "Part 2",
            "created_at": "2025-10-23 09:30:00",
            "result": "Defective",
            "defect_type": "Weld Cracks",
            "weld_location": "IB_WA3",
            "welds": weld(
                inner + outer,
                defects={"IB_WA3": "Weld Cracks", "IB_Z_2": "Short Weld"},
            ),
        },
        {
            "serial": "10474800000000003_10474900000000003",
            "part": "Part 3",
            "created_at": "2025-10-23 10:00:00",
            "result": "Defective",
            "defect_type": "Burn Through",
            "weld_location": "OB_WA2",
            "welds": weld(
                inner + outer,
                defects={
                    "OB_WA2": "Burn Through",
                    "OB_Z_5": "Porosity or Pits",
                    "IB_WA8": "Melt Back or Notching",
                },
            ),
        },
        {
            "serial": "10474800000000004_10474900000000004",
            "part": "Part 4",
            "created_at": "2025-10-23 10:30:00",
            "result": "Defective",
            "defect_type": "Porosity or Pits",
            "weld_location": "IB_Z_3",
            "welds": weld(
                inner + outer,
                defects={
                    "IB_WA4": "Porosity or Pits",
                    "OB_WA6": "Excessive Gap",
                    "OB_Z_3": "Off Location Weld",
                },
            ),
        },
        {
            "serial": "10474800000000005_10474900000000005",
            "part": "Part 5",
            "created_at": "2025-10-23 11:00:00",
            "result": "Healthy",
            "defect_type": "Healthy",
            "weld_location": "OB_WA7",
            "welds": weld(inner + outer),
        },
        {
            "serial": "10474800000000006_10474900000000006",
            "part": "Part 6",
            "created_at": "2025-10-23 11:30:00",
            "result": "Defective",
            "defect_type": "Short Weld",
            "weld_location": "IB_Z_5",
            "welds": weld(
                inner + outer,
                defects={
                    "IB_Z_5": "Short Weld",
                    "IB_WA2": "Overlap",
                    "OB_WA4": "Lack of Fusion (Cold Weld)",
                },
            ),
        },
        {
            "serial": "10474800000000007_10474900000000007",
            "part": "Part 7",
            "created_at": "2025-10-23 12:00:00",
            "result": "Healthy",
            "defect_type": "Healthy",
            "weld_location": "IB_WA9",
            "welds": weld(inner + outer),
        },
        {
            "serial": "10474800000000008_10474900000000008",
            "part": "Part 8",
            "created_at": "2025-10-23 12:30:00",
            "result": "Defective",
            "defect_type": "Excessive Gap",
            "weld_location": "OB_Z_9",
            "welds": weld(
                inner + outer,
                defects={
                    "OB_Z_9": "Excessive Gap",
                    "OB_WA10": "Undercut",
                    "IB_Z_6": "Skip or Discontinuation",
                },
            ),
        },
    ]

    return rows

# ──────────────────────────────────────────────────────────────
# State Class
# ──────────────────────────────────────────────────────────────
class ResultsState(rx.State):
    """State for the Inspections Results page."""

    # Filters
    search: str = ""
    result_filter: str = "All"
    date_range: str = "8 weeks"
    sort_desc: bool = True
    defect_type_filter: str = "All"
    weld_location_filter: str = "All"

    # Table / paging
    page: int = 1
    page_size: int = 10
    expanded_serial: str = ""

    # Dummy data
    rows: List[Dict[str, Union[str, int]]] = []

    # ───────────── Derived Data ─────────────
    @rx.var
    def filtered_rows(self) -> List[Dict[str, Union[str, int]]]:
        rows = self.rows

        # Result filter
        if self.result_filter and self.result_filter != "All":
            rows = [r for r in rows if r["result"] == self.result_filter]

        # Search
        q = self.search.strip().lower()
        if q:
            rows = [r for r in rows if q in str(r["serial"]).lower()]

        # Defect type filter
        if self.defect_type_filter != "All":
            rows = [r for r in rows if r.get("defect_type") == self.defect_type_filter]

        # Weld location filter
        if self.weld_location_filter != "All":
            rows = [r for r in rows if r.get("weld_location") == self.weld_location_filter]

        # Date range
        now = datetime.now()
        range_map = {
            "7 days": now - timedelta(days=7),
            "2 weeks": now - timedelta(weeks=2),
            "4 weeks": now - timedelta(weeks=4),
            "8 weeks": now - timedelta(weeks=8),
        }
        cutoff = range_map.get(self.date_range)
        if cutoff:
            rows = [
                r for r in rows
                if datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S") >= cutoff
            ]

        # Sort by created_at
        rows = sorted(rows, key=lambda r: r["created_at"], reverse=self.sort_desc)
        return rows

    @rx.var
    def total_results(self) -> int:
        return len(self.filtered_rows)

    @rx.var
    def total_pages(self) -> int:
        n = self.total_results
        return max(1, (n + self.page_size - 1) // self.page_size)

    @rx.var
    def page_rows(self) -> List[Dict[str, Union[str, int]]]:
        """Return plain list (Reflex handles conversion)."""
        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        return self.filtered_rows[start:end]

    # ───────────── Events ─────────────
    def set_search(self, v: str):
        self.search = v
        self.page = 1

    def clear_search(self):
        self.search = ""
        self.page = 1

    def set_filter(self, v: Optional[str]):
        self.result_filter = v or "All"
        self.page = 1

    def set_date_range(self, v: Optional[str]):
        self.date_range = v or "7 days"
        self.page = 1

    def toggle_sort(self):
        self.sort_desc = not self.sort_desc

    def next_page(self):
        if self.page < self.total_pages:
            self.page += 1

    def prev_page(self):
        if self.page > 1:
            self.page -= 1

    def toggle_expand(self, serial: str):
        self.expanded_serial = "" if self.expanded_serial == serial else serial

    def set_defect_type_filter(self, v: Optional[str]):
        self.defect_type_filter = v or "All"
        self.page = 1

    def set_weld_location_filter(self, v: Optional[str]):
        self.weld_location_filter = v or "All"
        self.page = 1
    
    def on_load(self):
        """Called when the page first loads to inject dummy data."""
        self.rows = generate_dummy_rows()


# ──────────────────────────────────────────────────────────────
# Components
# ──────────────────────────────────────────────────────────────
def _result_pill(result):
    return rx.text(
        result,
        as_="span",
        class_name=rx.cond(
            result == "Defective",
            "sr-result-pill pill-def",
            "sr-result-pill pill-ok",
        ),
    )


def _weld_pill(w):
    """Render a single weld pill (safe for dicts or Reflex vars)."""
    if hasattr(w, "to"):
        w = w.to(dict)
    elif isinstance(w, rx.Var):
        try:
            w = w.value or {}
        except Exception:
            w = {}
    if not isinstance(w, dict):
        w = {}

    # Extract values safely
    loc = w.get("location", "Unknown")
    status = w.get("status", "Healthy")

    # Ensure proper string type
    if status is None:
        status = "Healthy"
    status = str(status).strip()

    # Pick color class
    is_healthy = status.lower() == "healthy"
    color_class = "weld-healthy" if is_healthy else "weld-defect"

    return rx.box(
        rx.text(loc, class_name="weld-loc"),
        rx.text(status, class_name=f"weld-pill {color_class}"),
        class_name="weld-box",
    )

import copy

def _weld_grid(welds):
    """Render all welds grouped by IB/OB (properly showing defect data)."""
    # Normalize incoming welds list (avoid Reflex Var confusion)
    if isinstance(welds, rx.Var):
        try:
            welds = copy.deepcopy(welds.value or [])
        except Exception:
            welds = []
    elif hasattr(welds, "to"):
        welds = copy.deepcopy(welds.to(list))
    else:
        welds = copy.deepcopy(list(welds or []))

    # Build a direct lookup map
    weld_map = {}
    for w in welds:
        if isinstance(w, dict) and "location" in w and "status" in w:
            weld_map[w["location"]] = w["status"]

    def _pill_for_location(loc: str):
        # get exact status if available
        status = weld_map.get(loc)
        if not status:  # fallback if location not found
            status = random.choice(["Healthy"] + DEFECT_TYPES)
        return _weld_pill({"location": loc, "status": status})

    ib_locs = [loc for loc in WELD_LOCATIONS if loc.startswith("IB_")]
    ob_locs = [loc for loc in WELD_LOCATIONS if loc.startswith("OB_")]

    ib_grid = rx.box(
        rx.foreach(ib_locs, _pill_for_location),
        class_name="weld-grid",
    )

    ob_grid = rx.box(
        rx.foreach(ob_locs, _pill_for_location),
        class_name="weld-grid",
    )

    return rx.accordion.root(
        rx.accordion.item(header="Inner Body Welds", content=ib_grid),
        rx.accordion.item(header="Outer Body Welds", content=ob_grid),
        type="multiple",
        collapsible=True,
        class_name="sr-weld-accordion",
    )

def _row(item):
    """Main row with expand."""
    item = item.to(dict)
    serial = item["serial"]

    row = rx.box(
        rx.text(item["serial"], class_name="sr-serial sr-cell"),
        rx.text(item["part"], class_name="sr-cell"),
        rx.text(item["created_at"], class_name="sr-cell"),
        _result_pill(item["result"]),
        rx.button(
            rx.icon(
                "chevron-down",
                size=16,
                class_name=rx.cond(
                    ResultsState.expanded_serial == serial,
                    "sr-caret rot-180",
                    "sr-caret",
                ),
            ),
            class_name="sr-expand",
            on_click=lambda: ResultsState.toggle_expand(serial),
        ),
        class_name="sr-row sr-tr",
    )

    details = rx.box(
        _weld_grid(item.get("welds", [])),
        class_name="sr-subrow",
    )

    return rx.box(row, rx.cond(ResultsState.expanded_serial == serial, details, rx.fragment()))


def _table_header():
    sort_icon = rx.cond(
        ResultsState.sort_desc,
        rx.icon("chevron-down", size=16),
        rx.icon("chevron-up", size=16),
    )
    created_sort_btn = rx.button(
        rx.hstack(rx.text("Created At"), sort_icon, align="center", spacing="1"),
        on_click=ResultsState.toggle_sort,
        class_name="sr-sort",
    )
    return rx.box(
        rx.text("Serial Number"), rx.text("Part"), created_sort_btn,
        rx.text("Result"), rx.box(), class_name="sr-th sr-tr"
    )


def _table():
    return rx.box(
        _table_header(),
        rx.foreach(ResultsState.page_rows.to(list), _row),
        class_name="sr-card sr-table",
    )


def _footer():
    return rx.box(
        rx.text(
            f"Page {ResultsState.page} of {ResultsState.total_pages} — {ResultsState.total_results} results",
            class_name="sr-page-chip",
        ),
        rx.hstack(
            rx.button(rx.icon("chevron-left"), on_click=ResultsState.prev_page, disabled=ResultsState.page <= 1, class_name="sr-nav-btn"),
            rx.button(rx.icon("chevron-right"), on_click=ResultsState.next_page, disabled=ResultsState.page >= ResultsState.total_pages, class_name="sr-nav-btn"),
        ),
        class_name="sr-card sr-footer",
    )


def _toolbar():
    return rx.box(
        rx.hstack(
            # Filters section
            rx.hstack(
                rx.box(
                    rx.text("Result", class_name="sr-label"),
                    rx.select(
                        ["All", "Defective", "Healthy"],
                        value=ResultsState.result_filter,
                        on_change=ResultsState.set_filter,
                        class_name="sr-select",
                    ),
                    class_name="sr-field",
                ),
                rx.box(
                    rx.text("Date Range", class_name="sr-label"),
                    rx.select(
                        ["7 days", "2 weeks", "4 weeks", "8 weeks"],
                        value=ResultsState.date_range,
                        on_change=ResultsState.set_date_range,
                        class_name="sr-select",
                    ),
                    class_name="sr-field",
                ),
                rx.box(
                    rx.text("Defect Type", class_name="sr-label"),
                    rx.select(
                        ["All"] + DEFECT_TYPES,
                        value=ResultsState.defect_type_filter,
                        on_change=ResultsState.set_defect_type_filter,
                        class_name="sr-select",
                    ),
                    class_name="sr-field",
                ),
                rx.box(
                    rx.text("Weld Location", class_name="sr-label"),
                    rx.select(
                        ["All"] + WELD_LOCATIONS,
                        value=ResultsState.weld_location_filter,
                        on_change=ResultsState.set_weld_location_filter,
                        class_name="sr-select",
                    ),
                    class_name="sr-field",
                ),
                spacing="3",
                wrap="wrap",
            ),

            # Search box aligned right
            rx.hstack(
                rx.input(
                    placeholder="Search by serial number...",
                    value=ResultsState.search,
                    on_change=ResultsState.set_search,
                    class_name="sr-input",
                ),
                rx.button(
                    "Clear",
                    on_click=ResultsState.clear_search,
                    disabled=ResultsState.search == "",
                    class_name="sr-clear",
                ),
                class_name="sr-search",
            ),
            justify="between",
            width="100%",
        ),
        class_name="sr-card sr-toolbar",
    )


# ──────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────
def _css() -> rx.Component:
    return rx.html(
        """
        <style>
            .sr-title { font-size:1.5rem; font-weight:700; color:#0f172a; }
            .sr-subtitle { font-size:1rem; color:#475569; margin-bottom:6px; }
            .sr-shell { display:flex; justify-content:center; width:100%; min-height:100vh; background:#f8fafc; padding:24px; }
            .sr-page  { width:min(1180px, 100%); display:flex; flex-direction:column; gap:16px; }
            .sr-card { background:#fff; border:1px solid rgba(15,23,42,.08); border-radius:12px; box-shadow:0 2px 6px rgba(2,6,23,.05); }

            /* Toolbar */
.sr-toolbar {
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.sr-field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 160px;
}

.sr-label {
    color: #334155;
    font-weight: 600;
    font-size: 0.85rem;
}

.sr-select {
    border: 1px solid rgba(15,23,42,0.12);
    border-radius: 6px;
    padding: 4px 6px;
    background: #fff;
}

.sr-search {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: auto;
    margin-top: 20px;
}

.sr-input {
    width: 240px;
    border: 1px solid rgba(15,23,42,0.12);
    border-radius: 6px;
    padding: 6px 8px;
}

.sr-clear {
    border: 1px solid rgba(15,23,42,0.1);
    border-radius: 6px;
    background: #f8fafc;
    padding: 6px 10px;
    font-size: 0.8rem;
    cursor: pointer;
}

.sr-clear:hover {
    background: #e2e8f0;
}


            /* Table */
            .sr-table { width:100%; }
            .sr-th, .sr-tr { display:grid; grid-template-columns: 2.2fr 1.6fr 1.4fr 1.1fr 48px; align-items:center; gap:12px; justify-items:start; }
            .sr-th { padding:12px 16px; color:#475569; font-weight:700; }
            .sr-row { padding:14px 16px; border-top:1px solid rgba(15,23,42,.06); }
            .sr-serial { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color:#0f172a; }
            .sr-result-pill { width: 100px; padding:5px 10px; font-weight:500; font-size:.75rem; display:inline-block; text-align:center; border-radius:5px; }
            .pill-def { background:#fee2e2; color:#991b1b; }
            .pill-ok  { background:#d1fae5; color:#065f46; }

            .sr-subrow { background:#f9fafb; margin:8px 16px 0 16px; border:1px dashed rgba(15,23,42,.12); border-radius:8px; padding:10px 12px; color:#334155; }

            /* Pager */
            .sr-footer { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; }
            .sr-page-chip { color:#475569; }
            .sr-nav { display:flex; gap:8px; }
            .sr-nav-btn { width:32px; height:32px; border-radius:8px; display:grid; place-items:center; border:1px solid rgba(15,23,42,.10); }
            .sr-nav-btn:disabled { opacity:.4; cursor:not-allowed; }

            .sr-sort {
                background:transparent; border:none; padding:0; margin:0; color:#475569;
                font-weight:700; font-size:.9rem; display:inline-flex; align-items:center; gap:6px;
                cursor:pointer;
            }
            .sr-sort:hover { background:transparent; }
            .sr-cell { color:#0f172a; font-size:.75rem; }
            .sr-expand { width:28px; height:28px; border-radius:8px; display:grid; place-items:center;
                         background:#fff; color:#334155; cursor:pointer; }
            .sr-expand:hover { background:#f1f5f9; }
            .sr-caret { transition: transform .18s ease; }
            .sr-caret.rot-180 { transform: rotate(180deg); }

            /* Weld grid pills */
            .weld-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
                gap: 10px;
                padding-top: 10px;
            }
            .weld-pill {
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 600;
                text-align: center;
                font-size: 0.8rem;
            }
            .weld-healthy {
                background: #bbf7d0;
                color: #065f46;
            }
            .weld-defect {
                background: #fee2e2;
                color: #991b1b;
            }
            .weld-loc {
                font-weight: 700;
                font-size: 0.8rem;
                display: block;
                color: #0f172a;
            }
            .weld-box-wrapper { position: relative; }
            .weld-na { background: #e2e8f0; color: #475569; }
            
            /* ────────────────  WELD GRID + PILLS  ──────────────── */
.weld-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 10px;
    padding: 10px;
}

.weld-box {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 6px;
    border-radius: 8px;
    background: #fff;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}

.weld-loc {
    font-weight: 600;
    font-size: 0.8rem;
    color: #0f172a;
}

.weld-pill {
    border-radius: 6px;
    padding: 4px 8px;
    font-weight: 600;
    font-size: 0.75rem;
    text-align: center;
}

.weld-healthy {
    background: #bbf7d0;   /* light green */
    color: #065f46;
}

.weld-defect {
    background: #fee2e2;   /* light red */
    color: #991b1b;
}

/* ────────────────  ACCORDION SECTIONS  ──────────────── */
.sr-weld-accordion {
    border: 1px solid rgba(15,23,42,0.08);
    border-radius: 10px;
    background: #fff !important;
    overflow: hidden;
}

.sr-weld-accordion .AccordionItem {
    border-bottom: 1px solid rgba(15,23,42,0.06);
}

.sr-weld-accordion .AccordionHeader {
    font-weight: 600;
    font-size: 0.9rem;
    padding: 10px 14px;
    background: #f1f5f9 !important;
    color: #000 !important;
    cursor: pointer;
}

.sr-weld-accordion .AccordionHeader .AccordionTrigger {
    color: #000 !important;
}

.sr-weld-accordion .AccordionHeader .AccordionChevron {
    color: #000 !important;
}

.sr-weld-accordion .AccordionHeader .AccordionTrigger:hover {
    background: #e2e8f0 !important;
    color: #000 !important;
    border-radius: 6px;
}

.sr-weld-accordion .AccordionContent {
    padding: 12px 14px;
    background: #f9fafb !important;
}
        </style>
        """
    )


# ──────────────────────────────────────────────────────────────
# Page Layout (with CSS reinjected)
# ──────────────────────────────────────────────────────────────
def inspectra_line_view() -> rx.Component:
    return rx.box(
        _css(),
        rx.box(
            rx.text("Line View", class_name="sr-title"),
            rx.text(
                "Detailed view of inspection results for a specific production line.",
                class_name="sr-subtitle",
            ),
            _toolbar(),
            _table(),
            _footer(),
            class_name="sr-page",
        ),
        class_name="sr-shell",
        on_mount=ResultsState.on_load,  # 👈 ensures data loads when rendered
    )


