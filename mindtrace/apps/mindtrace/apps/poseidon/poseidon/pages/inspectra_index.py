# poseidon/pages/index.py
import reflex as rx
from typing import List, Dict, Union, Literal

# ────────────────────────── Types / State ──────────────────────────
MetricKind = Literal["Yield", "Defect Rate", "Uptime"]

class DashboardState(rx.State):
    # top metric strip (dummy)
    top_metrics: List[Dict[str, str]] = [
        {"icon": "book-open-check", "value": "94.2%",   "label": "Avg Yield Rate",   "delta": "+2.1%",  "trend": "up"},
        {"icon": "clock",           "value": "96.4%","label": "First Pass Yield",     "delta": "+1.2%",  "trend": "up"},
        {"icon": "percent",         "value": "2.4M",    "label": "Total Parts",      "delta": "+15.2%", "trend": "up"},
        {"icon": "bell-ring",       "value": "3",       "label": "Alerts",           "delta": "-8.3%",  "trend": "down"},
        {"icon": "alert-triangle",  "value": "1,247",   "label": "Total Defects",    "delta": "-8.3%",  "trend": "down"},
    ]

    # selected metric for the line chart tabs
    metric: MetricKind = "Yield"

    # table pagination
    page: int = 1
    page_size: int = 5

    # table rows (dummy)
    rows: List[Dict[str, Union[str, float, int]]] = [
        {"plant": "Lakewood",      "region": "US",     "yield": 96.8, "uptime": 94.2, "alerts": 2, "parts_produced": 94_500, "status": "Excellent"},
        {"plant": "Ramos",         "region": "Mexico", "yield": 94.1, "uptime": 91.8, "alerts": 5, "parts_produced": 90_100, "status": "Good"},
        {"plant": "Clanton",       "region": "US",     "yield": 93.7, "uptime": 89.4, "alerts": 8, "parts_produced": 61_800, "status": "Warning"},
        {"plant": "Battle Creek",  "region": "US",     "yield": 96.8, "uptime": 94.2, "alerts": 2, "parts_produced": 94_500, "status": "Excellent"},
        {"plant": "Warren",        "region": "US",     "yield": 94.1, "uptime": 91.8, "alerts": 5, "parts_produced": 90_100, "status": "Good"},
    ]

    # line chart dummy data keyed by metric
    @rx.var
    def line_data(self) -> List[Dict[str, Union[str, float]]]:
        months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

        # helper: force a list to the target length (pad with last value or trim)
        def _fit(xs: list[float], n: int) -> list[float]:
            if not xs:
                return [0.0] * n
            if len(xs) >= n:
                return xs[:n]
            return xs + [xs[-1]] * (n - len(xs))

        if self.metric == "Yield":
            lakewood  = [96, 92, 75, 72, 85, 78, 95]
            ramos     = [98, 96, 88, 70, 82, 67, 90]
            clanton   = [38, 29, 35, 25, 31, 40, 34]
        elif self.metric == "Defect Rate":
            lakewood  = [3.2, 3.6, 4.1, 3.9, 3.4, 3.8, 2.7]
            ramos     = [2.7, 2.8, 3.1, 3.3, 3.0, 3.5, 2.4]
            clanton   = [8.5, 9.1, 8.7, 9.8, 9.2, 8.9, 9.4]
        else:  # Uptime
            lakewood  = [94, 95, 93, 92, 96, 97, 98]
            ramos     = [92, 93, 91, 90, 94, 95, 96]
            clanton   = [86, 87, 85, 84, 88, 89, 90]

        # fit to 12 months
        lakewood  = _fit(lakewood,  len(months))
        ramos     = _fit(ramos,     len(months))
        clanton   = _fit(clanton,   len(months))

        return [
            {
                "month": m,
                "Lakewood": lakewood[i],
                "Ramos": ramos[i],
                "Clanton": clanton[i],
            }
            for i, m in enumerate(months)
        ]

    # pre-formatted rows for display; safe to iterate in UI via rx.foreach
    @rx.var
    def paged_rows(self) -> List[Dict[str, Union[str, int]]]:
        def status_to_class(s: str) -> str:
            s = s.lower()
            if s.startswith("excel"):
                return "excellent"
            if s.startswith("warn"):
                return "warning"
            if s.startswith("crit"):
                return "critical"
            return "good"

        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        out: List[Dict[str, Union[str, int]]] = []
        for r in self.rows[start:end]:
            status = str(r["status"])
            out.append({
                "plant":              str(r["plant"]),
                "region":             str(r["region"]),
                "yield_s":            f'{float(r["yield"]):.1f}%',
                "uptime_s":           f'{float(r["uptime"]):.1f}%',
                "alerts":             int(r["alerts"]),
                "parts_produced_s":   f'{int(r["parts_produced"]):,}',  # numeric, thousands separator
                "status":             status,
                "status_class":       status_to_class(status),
            })
        return out

    @rx.var
    def total_pages(self) -> int:
        n = len(self.rows)
        return (n + self.page_size - 1) // self.page_size

    def next_page(self):
        if self.page < self.total_pages:
            self.page += 1

    def prev_page(self):
        if self.page > 1:
            self.page -= 1

    def set_metric_yield(self): self.metric = "Yield"
    def set_metric_defects(self): self.metric = "Defect Rate"
    def set_metric_uptime(self): self.metric = "Uptime"


# ────────────────────────── CSS ──────────────────────────
def _css() -> rx.Component:
    return rx.html(
        """
        <style>
          @keyframes fadeInUp { from {opacity:0; transform: translateY(16px);} to {opacity:1; transform:none;} }

          .nf-shell { display:flex; justify-content:center; width:100%; min-height:100vh; padding:36px 20px; background:#f8fafc; }
          .nf-content { display:flex; flex-direction:column; align-items:flex-start; gap:24px; width:100%; box-sizing:border-box; }

          /* metric strip */
          .nf-metrics { display:grid; grid-template-columns: repeat(5, 1fr); gap:16px; width:100%; }
          .nf-metric {
            background:#fff; border:1px solid rgba(15,23,42,.06); border-radius:12px;
            box-shadow: 0 2px 6px rgba(2,6,23,.05); padding:16px 18px; display:flex; gap:12px; align-items:center;
            animation: fadeInUp .35s ease both;
          }
          .nf-metric-icon { width:36px; height:36px; border-radius:10px; display:grid; place-items:center; flex:0 0 auto; box-shadow: inset 0 0 0 1px rgba(30,64,175,.08);}
          .nf-metric-body { display:flex; flex-direction:column; gap:2px; min-width:0; }
          .nf-metric-value { font-weight:700; color:#0f172a; line-height:1.1; font-size:1.1rem; }
          .nf-metric-label { color:#475569; font-size:.75rem; }
          .nf-up{color:#16a34a} .nf-down{color:#dc2626}

          /* cards */
          .nf-card {
            background:#fff; border:1px solid rgba(15,23,42,.06); border-radius:14px;
            box-shadow: 0 6px 18px rgba(2,6,23,.06); width:100%;
          }
          .nf-card-head { display:flex; align-items:center; justify-content:space-between; padding:14px 16px; }
          .nf-title { font-weight:700; color:#0f172a; display:flex; gap:8px; align-items:center; }
          .nf-sub { color:#64748b; font-size:.9rem; }
          .nf-divider { height:1px; width:100%; background:rgba(15,23,42,.06); }

          /* tabs (simple buttons) */
          .nf-tabs { display:flex; gap:8px; background:#f1f5f9; padding:4px; border-radius:999px; }
          .nf-tab { border:none; background:transparent; padding:6px 10px; border-radius:999px; color:#334155; font-weight:600; cursor:pointer; }
          .nf-tab.active { background:#fff; box-shadow:0 1px 3px rgba(2,6,23,.08); color:#0f172a; }

          /* table-like list */
          .nf-table { width:100%; }
          .nf-th, .nf-tr {
            display: grid;
            grid-template-columns: 2fr 1fr 1fr 0.8fr 1.2fr;
            gap: 12px;
            align-items: center;
            }
          .nf-th { padding:12px 16px; color:#000; font-weight:700; }
          .nf-row {
            padding: 14px 16px;
            border-top: 1px solid rgba(15,23,42,.06);
            background: #fff;
            }

            .nf-row:nth-child(even) {
            background: #f9fafb;
            }
          .nf-cell-ellipsis { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
          .nf-badge { padding:4px 10px; border-radius:999px; font-weight:700; font-size:.82rem; display:inline-block; text-align:center; }
          .nf-badge.excellent { background:#d1fae5; color:#065f46; }
          .nf-badge.good      { background:#dbeafe; color:#1e40af; }
          .nf-badge.warning   { background:#ffedd5; color:#9a3412; }
          .nf-badge.critical  { background:#fee2e2; color:#991b1b; }
          .nf-link { color:#2563eb; font-weight:600; cursor:pointer; }

          .nf-pager { display:flex; align-items:center; justify-content:flex-end; gap:10px; padding:10px 12px 14px; }
          .nf-page-chip { color:#475569; display:flex; align-items:center; gap:4px; }
          .nf-nav-btn { width:32px; height:32px; border-radius:8px; display:grid; place-items:center; border:1px solid rgba(15,23,42,.08); cursor:pointer; }
          .nf-nav-btn:disabled { opacity:.4; cursor:not-allowed; }
        </style>
        """
    )

# ───────────────────── Building blocks ─────────────────────
def _metric_item(item):  # item is Var[dict]
    # Header row: icon on the left, value+label on the right
    header = rx.hstack(
        rx.box(
            rx.icon(tag=item["icon"], size=18),
            class_name=rx.cond(
                item["trend"] == "up",
                "nf-metric-icon nf-up",
                "nf-metric-icon nf-down",
            ),
        ),
        rx.box(
            rx.text(item["value"], class_name="nf-metric-value"),
            rx.text(item["label"], class_name="nf-metric-label"),
            class_name="nf-metric-body",
        ),
        align="center",
        spacing="2",
        width="100%",
    )

    # Delta row below
    delta_row = rx.hstack(
        rx.text(
            item["delta"],
            class_name=rx.cond(
                item["trend"] == "up",
                "nf-metric-label nf-up",
                "nf-metric-label nf-down",
            ),
        ),
        rx.text("vs last month", class_name="nf-metric-label"),
        spacing="1",
        align="center",
    )

    # Card item: stack header over delta
    return rx.box(
        rx.vstack(header, delta_row, align="start", spacing="1", width="100%"),
        class_name="nf-metric",
    )

def _metrics_strip() -> rx.Component:
    return rx.box(
        rx.foreach(DashboardState.top_metrics, _metric_item),
        class_name="nf-metrics",
    )

def _trend_tabs() -> rx.Component:
    return rx.box(
        rx.button(
            "Yield",
            class_name=rx.cond(DashboardState.metric == "Yield", "nf-tab active", "nf-tab"),
            on_click=DashboardState.set_metric_yield,
        ),
        rx.button(
            "Defect Rate",
            class_name=rx.cond(DashboardState.metric == "Defect Rate", "nf-tab active", "nf-tab"),
            on_click=DashboardState.set_metric_defects,
        ),
        # rx.button(
        #     "Uptime",
        #     class_name=rx.cond(DashboardState.metric == "Uptime", "nf-tab active", "nf-tab"),
        #     on_click=DashboardState.set_metric_uptime,
        # ),
        class_name="nf-tabs",
    )

def _performance_trends() -> rx.Component:
    return rx.box(
        rx.box(
            rx.vstack(
                rx.hstack(rx.icon("line-chart"), rx.text("Performance Trends"), class_name="nf-title"),
                rx.text("Top 3 manufacturing sites comparison", class_name="nf-sub"),
                align="start",
                spacing="1",
            ),
            _trend_tabs(),
            class_name="nf-card-head",
        ),
        rx.box(class_name="nf-divider"),
        rx.box(
            rx.recharts.line_chart(
                rx.recharts.cartesian_grid(stroke_dasharray="3 3"),
                rx.recharts.x_axis(data_key="month"),
                rx.recharts.y_axis(),
                rx.recharts.tooltip(),
                rx.recharts.legend(),
                rx.recharts.line(
                    type_="monotone", data_key="Lakewood",
                    stroke="#1E3A8A", dot={"r": 3, "fill": "#ffffff", "stroke": "#1E3A8A"}, stroke_width=2
                ),
                rx.recharts.line(
                    type_="monotone", data_key="Ramos",
                    stroke="#2563EB", stroke_opacity=0.9,
                    dot={"r": 3, "fill": "#ffffff", "stroke": "#2563EB"}, stroke_width=2
                ),
                rx.recharts.line(
                    type_="monotone", data_key="Clanton",
                    stroke="#60A5FA", stroke_opacity=0.85,
                    dot={"r": 3, "fill": "#ffffff", "stroke": "#60A5FA"}, stroke_width=2
                ),
                data=DashboardState.line_data,  # type: ignore
                width="100%", height=320, margin={"top": 8, "right": 12, "left": 0, "bottom": 0},
            ),
            padding="8px 10px 12px",
        ),
        class_name="nf-card",
    )

def _status_badge(status, status_class):  # both are Var[str]
    return rx.text(status, as_="span", class_name=f"nf-badge {status_class}")

def _table_header() -> rx.Component:
    return rx.box(
        rx.text("Plant Name", as_="span"),
        rx.text("Region", as_="span"),
        rx.text("Yield Rate", as_="span"),
        rx.text("Alerts", as_="span"),
        rx.text("Parts Produced", as_="span"),
        class_name="nf-th nf-tr",
        role="row",
    )


def _table_row(r):  # r is Var[dict]
    return rx.box(
        rx.text(r["plant"], as_="span", class_name="nf-cell-ellipsis"),
        rx.text(r["region"], as_="span"),
        rx.text(r["yield_s"], as_="span"),
        rx.text(r["alerts"], as_="span"),
        rx.text(r["parts_produced_s"], as_="span"),
        class_name="nf-row nf-tr",
        role="row",
    )


def _site_performance_table() -> rx.Component:
    pager = rx.box(
        rx.box(
            rx.text("Page ", as_="span", class_name="nf-page-chip"),
            rx.text(DashboardState.page, as_="span", class_name="nf-page-chip"),
            rx.text(" of ", as_="span", class_name="nf-page-chip"),
            rx.text(DashboardState.total_pages, as_="span", class_name="nf-page-chip"),
            class_name="nf-page-chip",
        ),
        rx.button(
            rx.icon("chevron-left", size=16),
            class_name="nf-nav-btn",
            on_click=DashboardState.prev_page,
            disabled=DashboardState.page <= 1,
        ),
        rx.button(
            rx.icon("chevron-right", size=16),
            class_name="nf-nav-btn",
            on_click=DashboardState.next_page,
            disabled=DashboardState.page >= DashboardState.total_pages,
        ),
        class_name="nf-pager",
    )

    return rx.box(
        rx.box(
            rx.vstack(
                rx.hstack(rx.icon("list-tree"), rx.text("Site Performance Comparison"), class_name="nf-title"),
                rx.text("Real-time performance metrics across all manufacturing sites", class_name="nf-sub"),
                align="start",
                spacing="1",
            ),
            rx.box(),  # right-side spacer
            class_name="nf-card-head",
        ),
        rx.box(class_name="nf-divider"),
        rx.box(
            _table_header(),
            rx.foreach(DashboardState.paged_rows, _table_row),
            class_name="nf-table",
        ),
        pager,
        class_name="nf-card",
    )

# ────────────────────────── Page ──────────────────────────
def index() -> rx.Component:
    return rx.box(
        _css(),
        rx.box(
            rx.box(
                _metrics_strip(),
                _performance_trends(),
                _site_performance_table(),
                class_name="nf-content",
            ),
            class_name="nf-shell",
        ),
        width="100%",
        min_height="100vh",
    )
