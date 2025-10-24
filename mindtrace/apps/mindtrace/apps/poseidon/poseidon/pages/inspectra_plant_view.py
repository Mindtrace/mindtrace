import random
import reflex as rx
from typing import List, Dict, Literal, Union

# ────────────────────────── Helpers ──────────────────────────
def _class_for_defect(p: float) -> str:
    if p <= 5:
        return "lv-soft green"
    if p <= 15:
        return "lv-soft amber"
    return "lv-soft red"

def _class_for_uptime(u: float) -> str:
    if u >= 90:
        return "lv-soft green"
    if u >= 75:
        return "lv-soft amber"
    return "lv-soft red"

# ────────────────────────── Constants ──────────────────────────
LineStatus = Literal["online", "idle", "error"]
Severity = Literal["ok", "warn", "critical"]

PALETTE = [
    "#184937", "#2563EB", "#DC2626", "#F59E0B", "#16A34A",
    "#7C3AED", "#06B6D4", "#D946EF", "#CA8A04", "#0891B2",
    "#F97316", "#0E7490", "#E11D48", "#4F46E5", "#84CC16",
    "#C026D3", "#0284C7", "#9A3412"
]

DEFECT_TYPES = [
    "Off Location Weld", "Weld Cracks", "Burn Through", "Porosity or Pits",
    "Melt Back or Notching", "Lack of Fusion (Cold Weld)", "Blow Hole",
    "Missing Weld", "Excessive Gap", "Undercut", "Crater", "Short Weld",
    "Skip or Discontinuation", "Overlap", "Unstable Weld", "Wire Stick",
    "Spatter", "Melt Through",
]

# ────────────────────────── State ──────────────────────────
class PlantViewState(rx.State):
    auto_refresh: bool = True
    live_indicator: bool = True
    range_filter: str = "Last 24h"
    selected_idx: int = 0

    total_parts: int = 12540
    defect_rate_overall: float = 3.4
    defect_trend_data: List[Dict[str, Union[str, float]]] = []
    defect_trend_colors: Dict[str, str] = {}
    alerts: List[Dict[str, str]] = []

    lines: List[Dict[str, Union[str, float, int]]] = [
        {"name": "Laser", "version": "v1.3.2", "status": "online", "uptime": 92.6, "defect_rate": 3.6,
         "last_inspection": "2 minutes ago", "severity": "ok", "alerts": 0,
         "uptime_cls": _class_for_uptime(92.6), "defect_cls": _class_for_defect(3.6)},
        {"name": "Mig66", "version": "v1.3.1", "status": "idle", "uptime": 84.1, "defect_rate": 7.8,
         "last_inspection": "8 minutes ago", "severity": "warn", "alerts": 1,
         "uptime_cls": _class_for_uptime(84.1), "defect_cls": _class_for_defect(7.8)},
        {"name": "Mig24", "version": "v1.3.0", "status": "error", "uptime": 72.3, "defect_rate": 23.3,
         "last_inspection": "16 minutes ago", "severity": "critical", "alerts": 18,
         "uptime_cls": _class_for_uptime(72.3), "defect_cls": _class_for_defect(23.3)},
        {"name": "MDX", "version": "v1.3.0", "status": "online", "uptime": 92.3, "defect_rate": 5.3,
         "last_inspection": "14 minutes ago", "severity": "ok", "alerts": 0,
         "uptime_cls": _class_for_uptime(92.3), "defect_cls": _class_for_defect(5.3)},
    ]
    
    selected_defect_1: str = "Weld Cracks"
    selected_defect_2: str = "Porosity or Pits"

    @rx.var
    def filtered_defect_trend_data(self) -> List[Dict[str, Union[str, float]]]:
        """Ensure 'All Defects' line is always above sub-defects."""
        data_with_all = []
        for row in self.defect_trend_data:
            # Get all numeric defect values for that week
            defect_values = [v for k, v in row.items() if k != "week"]
            if not defect_values:
                continue

            # Instead of average, base on max + a small margin (e.g. +10%)
            max_val = max(defect_values)
            adjusted = round(max_val + 1.5, 1)  # 10% higher than top defect

            new_row = dict(row)
            new_row["All Defects"] = adjusted
            data_with_all.append(new_row)
        return data_with_all


    def set_defect_1(self, value: str):
        self.selected_defect_1 = value

    def set_defect_2(self, value: str):
        self.selected_defect_2 = value

    @rx.var
    def lines_with_index(self) -> List[Dict[str, Union[str, float, int]]]:
        return [dict(item, idx=i) for i, item in enumerate(self.lines)]

    @rx.var
    def alerts_count(self) -> int:
        return len(self.alerts)

    def toggle_refresh(self): self.auto_refresh = not self.auto_refresh
    def toggle_live(self): self.live_indicator = not self.live_indicator

    def update_kpis(self):
        r = random.Random()
        if self.range_filter == "Last 24h":
            self.total_parts = r.randint(400, 1500)
            self.defect_rate_overall = round(r.uniform(2.5, 5.5), 1)
        elif self.range_filter == "1 Week":
            self.total_parts = r.randint(6000, 9000)
            self.defect_rate_overall = round(r.uniform(3.0, 6.0), 1)
        else:
            self.total_parts = r.randint(11000, 18000)
            self.defect_rate_overall = round(r.uniform(2.8, 7.5), 1)

        pool = [
            {"icon": "alert-triangle", "title": "Defect rate exceeded threshold", "time": "1 min ago"},
            {"icon": "bell-ring", "title": "Maintenance reminder", "time": "3 mins ago"},
            {"icon": "circle-alert", "title": "Model anomaly detected", "time": "2 mins ago"},
            {"icon": "video-off", "title": "Camera feed lost", "time": "4 mins ago"},
        ]
        self.alerts = random.sample(pool, k=random.randint(2, 4))

    def set_range_filter(self, value: str):
        self.range_filter = value
        self.update_kpis()
        self.generate_defect_trend()

    def select_line(self, idx: int):
        if not (0 <= idx < len(self.lines)): return
        self.selected_idx = idx
        self.update_kpis()
        self.generate_defect_trend()

    def generate_defect_trend(self):
        r = random.Random()
        weeks = ["W1", "W2", "W3", "W4", "W5", "W6"]
        data = []
        for w in weeks:
            row = {"week": w}
            for d in DEFECT_TYPES:
                row[d] = round(r.uniform(1.0, 12.0), 1)
            data.append(row)
        self.defect_trend_data = data
        self.defect_trend_colors = {d: PALETTE[i % len(PALETTE)] for i, d in enumerate(DEFECT_TYPES)}

# ────────────────────────── CSS ──────────────────────────
def _css() -> rx.Component:
    return rx.html("""
    <style>
      .lv-shell { display:flex; justify-content:center; width:100%; background:#f8fafc; padding:22px; }
      .lv-page { width:min(1180px, 100%); display:flex; flex-direction:column; gap:14px; }
      .lv-header { display:flex; justify-content:space-between; align-items:center; }
      .lv-title { font-size:1.4rem; font-weight:800; color:#0f172a; }
      .lv-sub { color:#64748b; }
      .lv-dot { width:8px; height:8px; border-radius:999px; background:#22c55e; display:inline-block; }
      .lv-dot.off { background:#94a3b8; }
      .lv-chip { padding:4px 10px; border-radius:999px; font-weight:700; font-size:.78rem; display:inline-flex; gap:6px; align-items:center; border:1px solid rgba(15,23,42,.10); background:#fff; }
      .lv-chip-toggle { cursor:pointer; }
      .lv-chip-toggle:hover { background:#f1f5f9; }

      /* SCROLLABLE TOP STRIP */
      .lv-top-strip { display:grid; grid-auto-flow: column; grid-auto-columns: minmax(320px, 1fr); gap:35px; overflow-x:auto; padding-bottom:6px; scroll-snap-type:x mandatory; }
      .lv-top-strip::-webkit-scrollbar { height:8px; }
      .lv-top-strip::-webkit-scrollbar-thumb { background:rgba(15,23,42,.18); border-radius:8px; }
      .lv-top-hr { height:4px; background:rgba(15,23,42,.08); border-radius:999px; }

      .lv-grid-main { display:grid; grid-template-columns: 1fr; gap:14px; }
      .lv-grid-bottom { display:grid; grid-template-columns: 1fr; gap:14px; }

      .lv-card { background:#fff; border:1px solid rgba(15,23,42,.08); border-radius:12px; box-shadow:0 2px 6px rgba(2,6,23,.05); transition: box-shadow .15s, border-color .15s; }
      .lv-card.snap { cursor: default; border-color: rgba(15,23,42,.06); }
      .lv-card.snap:hover { box-shadow: none; }
      .lv-card.sel { border-color:#60a5fa; box-shadow:0 0 0 2px rgba(37,99,235,.25); }
      .lv-card-pad { padding:14px; }
      .lv-card-full-width { width:100%; }

      .lv-line-name { font-weight:700; color:#0f172a; }
      .lv-line-ver { color:#94a3b8; font-weight:600; }
      .lv-stat-row { display:grid; grid-template-columns: 1fr 1fr; gap:10px; }

      .lv-kpi { border:1px solid rgba(15,23,42,.08); border-radius:10px; padding:10px 12px; background:#fff; }
      .lv-kpi .label { color:#64748b; }
      .lv-kpi .value { color:#0f172a; font-weight:800; }
      .lv-kpi .sub { color:#94a3b8; font-size:.8rem; }

      /* Images */
      .lv-defect-images { display:flex; gap:10px; }
      .lv-img-card { position:relative; border-radius:10px; overflow:hidden; flex:1; height:220px; box-shadow:0 2px 6px rgba(2,6,23,.05); border:1px solid rgba(15,23,42,.08); }
      .lv-img-overlay { position:absolute; bottom:0; left:0; right:0; background:rgba(15,23,42,.7); color:#f8fafc; font-weight:700; padding:6px 10px; font-size:0.9rem; }

      /* Buttons & Alerts */
      .lv-actions { width:100%; display:flex; flex-direction:column; gap:10px; }
      .lv-actions .btn { width:100%; padding:10px 12px; border-radius:10px; border:1px solid rgba(15,23,42,.10); background:#f8fafc; display:flex; align-items:center; gap:8px; font-weight:600; color:#334155; }
      .lv-actions .btn:hover { background:#eef2f7; }
      .lv-actions .btn.danger { background:#fff; border-color:#fecaca; color:#991b1b; }
      .lv-actions .btn.danger:hover { background:#fff1f1; }

      .lv-alerts-list { display:flex; flex-direction:column; gap:8px; width:100%; }
      .lv-alert-item { display:flex; gap:10px; align-items:flex-start; border:1px solid rgba(15,23,42,.08); border-radius:10px; padding:10px; background:#fff; gap:10px; }
      .lv-alert-title { color:#0f172a; font-weight:700; }
      .lv-alert-time { color:#94a3b8; font-size:.85rem; }
      /* ───────────── Live Alerts Card Layout ───────────── */
    .lv-alerts-card {
    display: flex;
    flex-direction: column;
    height: 190px;
    overflow: hidden; /* keeps everything inside card bounds */
    }

    .lv-alerts-scrollable {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    }

    .lv-alerts-scrollable::-webkit-scrollbar {
    width: 6px;
    }

    .lv-alerts-scrollable::-webkit-scrollbar-thumb {
    background: rgba(15,23,42,0.25);
    border-radius: 8px;
    }

      .lv-legend-wrap { display:grid; grid-template-columns: 1fr 1fr; gap:8px 14px; max-height:260px; overflow:auto; padding-right:6px; }
      .lv-legend-item { display:flex; align-items:center; gap:10px; }
      .lv-legend-name { color:#0f172a; font-weight:600; font-size:.86rem; }
      .lv-pad { padding:10px 12px 12px; }
      .lv-live-height { height:446px; }
      .lv-shell { display:flex; justify-content:center; width:100%; background:#f8fafc; padding:22px; }
          .lv-page  { width:min(1180px, 100%); display:flex; flex-direction:column; gap:14px; }

          .lv-header { display:flex; justify-content:space-between; align-items:center; }
          .lv-title  { font-size:1.4rem; font-weight:800; color:#0f172a; }
          .lv-sub    { color:#64748b; }

          .lv-dot { width:8px; height:8px; border-radius:999px; background:#22c55e; display:inline-block; }
          .lv-dot.off { background:#94a3b8; }

          .lv-chip { padding:4px 10px; border-radius:999px; font-weight:700; font-size:.78rem; display:inline-flex; gap:6px; align-items:center; border:1px solid rgba(15,23,42,.10); background:#fff; }
          .lv-chip-toggle { cursor:pointer; }
          .lv-chip-toggle:hover { background:#f1f5f9; }

          /* SCROLLABLE TOP STRIP */
          .lv-top-strip {
            display:grid;
            grid-auto-flow: column;
            grid-auto-columns: minmax(320px, 1fr);
            gap:35px;
            overflow-x:auto;
            padding-bottom:6px;
            scroll-snap-type:x mandatory;
          }
          .lv-top-strip::-webkit-scrollbar { height:8px; }
          .lv-top-strip::-webkit-scrollbar-thumb { background:rgba(15,23,42,.18); border-radius:8px; }
          .lv-top-hr { height:4px; background:rgba(15,23,42,.08); border-radius:999px; }

          .lv-grid-main { display:grid; grid-template-columns: 2fr 1fr; gap:14px; }
          .lv-grid-bottom { display:grid; grid-template-columns: 1fr 1fr; gap:14px; }

          .lv-card { background:#fff; border:1px solid rgba(15,23,42,.08); border-radius:12px; box-shadow:0 2px 6px rgba(2,6,23,.05); transition: box-shadow .15s, border-color .15s; }
          .lv-card.snap { scroll-snap-align:start; }
          .lv-card.sel  { border-color:#60a5fa; box-shadow:0 0 0 2px rgba(37,99,235,.25), 0 2px 6px rgba(2,6,23,.05); }
          .lv-card.selectable { cursor:pointer; }
          .lv-card-pad { padding:14px; }

          .lv-line { display:grid; grid-template-rows:auto auto; gap:10px; }
          .lv-line-head { display:flex; justify-content:space-between; align-items:center; }
          .lv-line-name { font-weight:700; color:#0f172a; }
          .lv-line-ver  { color:#94a3b8; font-weight:600; }
          .lv-stat-row { display:grid; grid-template-columns: 1fr 1fr; gap:10px; }
          .lv-meta { display:grid; grid-template-columns: 1fr 1fr; gap:10px; color:#64748b; }
          .lv-meta b { color:#0f172a; }

          .chip-online  { background:#ecfdf5; color:#065f46; border-color:rgba(22,163,74,.25); }
          .chip-idle    { background:#fff7ed; color:#9a3412; border-color:rgba(234,88,12,.25); }
          .chip-error   { background:#fee2e2; color:#991b1b; border-color:rgba(220,38,38,.25); }

          .pill-ok       { background:#d1fae5; color:#065f46; }
          .pill-warn     { background:#ffedd5; color:#9a3412; }
          .pill-critical { background:#fee2e2; color:#991b1b; }
          .pill { padding:4px 8px; border-radius:999px; font-weight:700; font-size:.75rem; display:inline-block; }

          /* soft percentage pills inside top cards */
          .lv-soft { padding:2px 6px; border-radius:6px; font-weight:700; font-size:.80rem; display:inline-flex; align-items:center; gap:2px; }
          .lv-soft.green { background:#ecfdf5; color:#047857; }
          .lv-soft.amber { background:#fff7ed; color:#9a3412; }
          .lv-soft.red   { background:#fee2e2; color:#991b1b; }

          /* Live panel */
          .lv-section-title { display:flex; align-items:center; gap:8px; font-weight:800; color:#0f172a; }
          .lv-feed { height:270px; border-radius:10px; background:#0b1220; color:#e2e8f0; display:grid; place-items:center; position:relative; overflow:hidden; }
          .lv-feed-watermark { opacity:.7; text-align:center; line-height:1.2; }
          .lv-feed-badge { position:absolute; top:10px; left:10px; background:#fee2e2; color:#991b1b; border:1px solid rgba(220,38,38,.18); border-radius:8px; padding:4px 8px; font-weight:800; font-size:.75rem; }
          .lv-feed-clock { position:absolute; top:10px; right:10px; background:rgba(15,23,42,.9); color:#e2e8f0; border-radius:6px; padding:4px 8px; font-weight:700; font-size:.75rem; }

          .lv-kpi-grid { display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin-top:10px; }
          .lv-kpi { border:1px solid rgba(15,23,42,.08); border-radius:10px; padding:10px 12px; background:#fff; }
          .lv-kpi .label { color:#64748b; }
          .lv-kpi .value { color:#0f172a; font-weight:800; }
          .lv-kpi .sub   { color:#94a3b8; font-size:.8rem; }

          /* Actions & Alerts */
          .lv-actions .btn { width:100%; padding:10px 12px; border-radius:10px; border:1px solid rgba(15,23,42,.10); background:#f8fafc; display:flex; align-items:center; gap:8px; font-weight:600; color:#334155; }
          .lv-actions .btn:hover { background:#eef2f7; }
          .lv-actions .btn.danger { background:#fff; border-color:#fecaca; color:#991b1b; }
          .lv-actions .btn.danger:hover { background:#fff1f1; }
          .lv-actions-panel { width:100%; }

          .lv-alerts-list { display:flex; flex-direction:column; gap:8px; }
          .lv-alert-item { display:flex; align-items:flex-start; gap:10px; border:1px solid rgba(15,23,42,.08); border-radius:10px; padding:10px; background:#fff; }
          .lv-alert-time { color:#94a3b8; font-size:.85rem; }
          .lv-alert-title { color:#0f172a; font-weight:700; }

          /* Defect bars */
          .lv-hbar-row { display:grid; grid-template-columns: 1fr 4fr 42px; gap:10px; align-items:center; }
          .lv-hbar-track { background:#e5e7eb; border-radius:999px; height:10px; overflow:hidden; }
          .lv-hbar-fill { background:#60a5fa; height:100%; border-radius:999px; }

          .lv-pad { padding:10px 12px 12px; }
          /* Legend for many items */
        .lv-legend-wrap { display:grid; grid-template-columns: 1fr 1fr; gap:8px 14px; max-height:260px; overflow:auto; padding-right:6px; }
        .lv-legend-item { display:flex; align-items:center; gap:10px; min-width:0; }
        .lv-legend-swatch { width:12px; height:12px; border-radius:3px; flex:0 0 auto; box-shadow: inset 0 0 0 1px rgba(0,0,0,.08); }
        .lv-legend-texts { display:flex; flex-direction:column; gap:2px; min-width:0; }
        .lv-legend-name { color:#0f172a; font-weight:600; font-size:.86rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .lv-legend-sub  { color:#64748b; font-size:.78rem; }
        .lv-defect-grid { display:grid; grid-template-columns: 1fr 1fr; gap:12px; align-items:start; }
        @media (max-width: 920px) { .lv-defect-grid { grid-template-columns: 1fr; } }

    </style>
    """)

# ───────────────────── Small building blocks ─────────────────────
def _status_chip(status) -> rx.Component:
    label = rx.cond(status == "online", "Online", rx.cond(status == "idle", "Idle", "Error"))
    cls = rx.cond(
        status == "online", "lv-chip chip-online",
        rx.cond(status == "idle", "lv-chip chip-idle", "lv-chip chip-error"),
    )
    return rx.box(
        rx.icon("dot", size=14),
        rx.text(label, as_="span"),
        class_name=cls,
    )


def _severity_pill(sev):
    label = rx.cond(sev == "ok", "Pass", rx.cond(sev == "warn", "Warning", "Critical"))
    cls = rx.cond(sev == "ok", "pill pill-ok", rx.cond(sev == "warn", "pill pill-warn", "pill pill-critical"))
    return rx.text(label, as_="span", class_name=cls)


def _percent_pill(val, pill_cls) -> rx.Component:
    return rx.box(
        rx.text(f"{val}%", as_="span"),
        class_name=pill_cls,
    )



# ────────────────────────── KPI & Cards ──────────────────────────
def _kpi(title, value_node, sub): return rx.box(rx.text(title, class_name="label"), value_node, rx.text(sub, class_name="sub"), class_name="lv-kpi")
def _kpi_value_plain(v): return rx.text(v, class_name="value")
def _kpi_value_pct(v): return rx.hstack(rx.text(v, class_name="value"), rx.text("%", class_name="value"))

def _top_line_card(item) -> rx.Component:
    # Simplify class – no selectable / on_click
    card_cls = rx.cond(
        item["severity"] == "critical",
        "lv-card snap acc",   # highlight critical
        "lv-card snap",       # normal card
    )

    return rx.box(
        rx.box(
            # ───────────── Header (name + version + status) ─────────────
            rx.hstack(
                rx.text(item["name"], class_name="lv-line-name"),
                rx.text(item["version"], class_name="lv-line-ver"),
                rx.spacer(),
                _status_chip(item["status"]),
                align="center",
            ),

            # ───────────── Uptime / Defect Rate ─────────────
            rx.box(
                rx.box(
                    rx.text("Uptime Today", class_name="lv-sub"),
                    _percent_pill(item["uptime"], item["uptime_cls"]),
                    class_name="lv-card-pad",
                ),
                rx.box(
                    rx.text("Defect Rate", class_name="lv-sub"),
                    _percent_pill(item["defect_rate"], item["defect_cls"]),
                    class_name="lv-card-pad",
                ),
                class_name="lv-stat-row",
            ),

            # ───────────── Last Inspection ─────────────
            rx.hstack(
                rx.text("Inspection", class_name="lv-sub"),
                rx.text(item["last_inspection"], class_name="lv-line-name"),
                class_name="lv-card-pad",
            ),

            # ───────────── Status + Alerts ─────────────
            rx.box(
                rx.text(
                    rx.fragment(
                        rx.text("Status ", as_="span", class_name="lv-sub"),
                        _severity_pill(item["severity"])
                    )
                ),
                rx.text(
                    rx.fragment(
                        rx.text("Alerts ", as_="span", class_name="lv-sub"),
                        rx.text(item["alerts"], as_="span", class_name="lv-line-name"),
                    )
                ),
                class_name="lv-meta lv-card-pad",
            ),
        ),
        class_name=card_cls,
        min_width="300px",
        padding="15px",
    )

def _top_cards() -> rx.Component:
    return rx.box(
        rx.foreach(PlantViewState.lines_with_index, _top_line_card),
        class_name="lv-top-strip"
    )


# ───────────────────── Live Overview ─────────────────────
def _live_panel():
    head = rx.hstack(
        rx.hstack(rx.icon("bar-chart-3"), rx.text(" Live Overview", weight="medium"), align="center", spacing="2"),
        rx.spacer(),
        rx.select(["Last 24h", "1 Week", "1 Month"], value=PlantViewState.range_filter, on_change=PlantViewState.set_range_filter, size="2", class_name="lv-chip lv-chip-toggle"),
        align="center", justify="between", padding="12px 14px",
    )

    kpi_row = rx.hstack(
        _kpi("Total Parts Produced", _kpi_value_plain(PlantViewState.total_parts), f"({PlantViewState.range_filter})"),
        _kpi("Defect Rate", _kpi_value_pct(PlantViewState.defect_rate_overall), "of Total"),
        spacing="8", align="center", padding="12px 14px",
    )

    img_map = {
        "Last 24h": ("/defect.png", "/weld.png"),
        "1 Week": ("/defect.png", "/weld.png"),
        "1 Month": ("/defect.png", "/weld.png"),
    }
    common, weld = img_map.get(PlantViewState.range_filter, img_map["Last 24h"])
    images = rx.box(
        rx.box(rx.image(src=common, width="100%", height="100%", object_fit="cover"), rx.box("Most Common Defect: Burn Through", class_name="lv-img-overlay"), class_name="lv-img-card"),
        rx.box(rx.image(src=weld, width="100%", height="100%", object_fit="cover"), rx.box("Most Defective Weld: Weld 7", class_name="lv-img-overlay"), class_name="lv-img-card"),
        class_name="lv-defect-images", padding="12px 14px",
    )

    return rx.box(head, kpi_row, images, class_name="lv-card lv-card-full-width lv-live-height")

# ───────────────────── Actions ─────────────────────
def _actions_panel():
    return rx.box(
        rx.hstack(rx.icon("settings"), rx.text(" Quick Actions", weight="medium"), class_name="lv-card-pad"),
        rx.box(
            rx.button(rx.icon("rotate-cw"), "Raise Issue", class_name="btn"),
            rx.button(rx.icon("download"), "Download CSV", class_name="btn"),
            rx.button(rx.icon("images"), "Export Report", class_name="btn"),
            rx.button(rx.icon("wrench"), "Trigger Maintenance", class_name="btn danger"),
            class_name="lv-card-pad lv-actions",
        ),
        class_name="lv-card lv-card-full-width",
    )

# ───────────────────── Live Alerts ─────────────────────
def _alerts_panel():
    return rx.box(
        rx.hstack(
            rx.icon("bell-ring"),
            rx.text(" Live Alerts", weight="medium"),
            class_name="lv-card-pad",
        ),
        rx.box(
            rx.foreach(
                PlantViewState.alerts,
                lambda a: rx.box(
                    rx.icon(a["icon"], color="#ef4444"),
                    rx.box(
                        rx.text(a["title"], class_name="lv-alert-title"),
                        rx.text(a["time"], class_name="lv-alert-time"),
                    ),
                    class_name="lv-alert-item",
                ),
            ),
            class_name="lv-card-pad lv-alerts-scrollable",  # new class here
        ),
        class_name="lv-card lv-alerts-card lv-card-full-width",
    )

# ───────────────────── Defect Breakdown Chart ─────────────────────
def _defect_breakdown_chart():
    # Dropdown selectors
    selectors = rx.hstack(
        rx.box(
            rx.text("Compare A:", class_name="lv-sub"),
            rx.select(
                DEFECT_TYPES,
                value=PlantViewState.selected_defect_1,
                on_change=PlantViewState.set_defect_1,
                size="2",
                class_name="lv-chip lv-chip-toggle",
            ),
        ),
        rx.box(
            rx.text("Compare B:", class_name="lv-sub"),
            rx.select(
                DEFECT_TYPES,
                value=PlantViewState.selected_defect_2,
                on_change=PlantViewState.set_defect_2,
                size="2",
                class_name="lv-chip lv-chip-toggle",
            ),
        ),
        spacing="5",
        align="center",
        justify="end",
        padding="0 14px 12px",
    )

    # Base lines (put All Defects LAST so it renders on top)
    line_1 = rx.recharts.line(
        type_="monotone",
        data_key=PlantViewState.selected_defect_1,
        stroke=PlantViewState.defect_trend_colors[PlantViewState.selected_defect_1],
        stroke_width=2,
        dot={"r": 2, "fill": "#fff"},
    )

    line_2 = rx.recharts.line(
        type_="monotone",
        data_key=PlantViewState.selected_defect_2,
        stroke=PlantViewState.defect_trend_colors[PlantViewState.selected_defect_2],
        stroke_width=2,
        dot={"r": 2, "fill": "#fff"},
    )

    # All Defects line — thicker + darker + rendered last (on top)
    all_defects_line = rx.recharts.line(
        type_="monotone",
        data_key="All Defects",
        stroke="#111111",  # dark gray / black tone
        stroke_width=3,
        dot={"r": 3, "fill": "#fff"},
        stroke_opacity=0.95,
    )

    return rx.box(
        rx.box(
            rx.hstack(
                rx.icon("activity"),
                rx.text(" Defect Trend Comparison By Defect Type", weight="medium"),
                rx.spacer(),
                selectors,
                align="center",
                padding="12px",
            ),
        ),
        rx.box(
            rx.recharts.line_chart(
                rx.recharts.cartesian_grid(stroke_dasharray="3 3"),
                rx.recharts.x_axis(data_key="week"),
                rx.recharts.y_axis(domain=[0, 12]),
                rx.recharts.tooltip(),
                rx.recharts.legend(),
                # order matters: others first, then All Defects
                line_1,
                line_2,
                all_defects_line,
                data=PlantViewState.filtered_defect_trend_data,
                width="100%",
                height=350,
            ),
            class_name="lv-pad",
        ),
        class_name="lv-card",
    )



# ────────────────────────── Page ──────────────────────────
def inspectra_plant_view() -> rx.Component:
    header = rx.box(
        rx.box(
            rx.text("Plant View", class_name="lv-title"),
            rx.text("Real-time production line monitoring", class_name="lv-sub"),
        ),
        rx.hstack(
            rx.box(
                rx.text("Auto Refresh", as_="span"),
                rx.box(class_name=rx.cond(PlantViewState.auto_refresh, "lv-dot", "lv-dot off")),
                class_name="lv-chip lv-chip-toggle",
                on_click=PlantViewState.toggle_refresh,
            ),
            rx.box(
                rx.box(class_name=rx.cond(PlantViewState.live_indicator, "lv-dot", "lv-dot off")),
                rx.text(" Live", as_="span"),
                class_name="lv-chip",
                on_click=PlantViewState.toggle_live,
            ),
            align="center",
            gap="8px",
        ),
        class_name="lv-header",
    )

    main = rx.hstack(
        rx.box(_live_panel(), flex="2"),  # left
        rx.vstack(
            _actions_panel(),
            _alerts_panel(),
            gap="14px",
            flex="1",  # right stacked
            width="100%",
        ),
        spacing="7",
        align="start",
        width="100%",
        height="476px",
    )

    return rx.box(
        _css(),
        rx.box(
            header,
            _top_cards(),
            main,
            _defect_breakdown_chart(),
            class_name="lv-page",
        ),
        class_name="lv-shell",
        on_mount=PlantViewState.generate_defect_trend(),
    )


