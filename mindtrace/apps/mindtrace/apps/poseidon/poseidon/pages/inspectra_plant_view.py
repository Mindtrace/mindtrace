# poseidon/pages/live_view.py
import random
import reflex as rx
from typing import List, Dict, Literal, Union

# Drop the pie chart, change it to total parts produced and defect rate, toggle for time range (today, 7d, 30d)

# ────────────────────────── Helpers (pure Python) ──────────────────────────
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


# ────────────────────────── State ──────────────────────────
LineStatus = Literal["online", "idle", "error"]
Severity   = Literal["ok", "warn", "critical"]

PALETTE = [
    "#2563eb",  # blue
    "#16a34a",  # green
    "#f59e0b",  # amber
    "#dc2626",  # red
    "#7c3aed",  # violet
    "#06b6d4",  # cyan
]

DEFECT_TYPES = [
    "Off Location Weld",
    "Weld Cracks",
    "Burn Through",
    "Porosity or Pits",
    "Melt Back or Notching",
    "Lack of Fusion (Cold Weld)",
    "Blow Hole",
    "Missing Weld",
    "Excessive Gap",
    "Undercut",
    "Crater",
    "Short Weld",
    "Skip or Discontinuation",
    "Overlap",
    "Unstable Weld",
    "Wire Stick",
    "Spatter",
    "Melt Through",
]

class PlantViewState(rx.State):
    # header toggles
    auto_refresh: bool = True
    live_indicator: bool = True

    # which line is selected in the top strip
    selected_idx: int = 0
    
    # defect types (active line) — full list with colors for the pie
    defects: List[Dict[str, Union[str, int]]] = [
        {"type": "Off Location Weld",            "count": 34, "fill": PALETTE[0]},
        {"type": "Weld Cracks",                  "count": 28, "fill": PALETTE[1]},
        {"type": "Burn Through",                 "count": 12, "fill": PALETTE[2]},
        {"type": "Porosity or Pits",             "count": 19, "fill": PALETTE[3]},
        {"type": "Melt Back or Notching",        "count": 22, "fill": PALETTE[4]},
        {"type": "Lack of Fusion (Cold Weld)",   "count": 17, "fill": PALETTE[5]},
        {"type": "Blow Hole",                    "count": 11, "fill": PALETTE[0]},
        {"type": "Missing Weld",                 "count": 9,  "fill": PALETTE[1]},
        {"type": "Excessive Gap",                "count": 13, "fill": PALETTE[2]},
        {"type": "Undercut",                     "count": 16, "fill": PALETTE[3]},
        {"type": "Crater",                       "count": 7,  "fill": PALETTE[4]},
        {"type": "Short Weld",                   "count": 14, "fill": PALETTE[5]},
        {"type": "Skip or Discontinuation",      "count": 10, "fill": PALETTE[0]},
        {"type": "Overlap",                      "count": 8,  "fill": PALETTE[1]},
        {"type": "Unstable Weld",                "count": 6,  "fill": PALETTE[2]},
        {"type": "Wire Stick",                   "count": 5,  "fill": PALETTE[3]},
        {"type": "Spatter",                      "count": 21, "fill": PALETTE[4]},
        {"type": "Melt Through",                 "count": 4,  "fill": PALETTE[5]},
    ]

    # top cards (dummy) — include precomputed pill classes so UI never compares Vars.
    lines: List[Dict[str, Union[str, float, int]]] = [
        {
            "name": "Laser",
            "version": "v1.3.2",
            "status": "online",
            "uptime": 92.6,
            "defect_rate": 3.6,
            "last_inspection": "2 minutes ago",
            "severity": "ok",
            "alerts": 0,
            "uptime_cls": _class_for_uptime(92.6),
            "defect_cls": _class_for_defect(3.6),
        },
        {
            "name": "Mig66",
            "version": "v1.3.1",
            "status": "idle",
            "uptime": 84.1,
            "defect_rate": 7.8,
            "last_inspection": "8 minutes ago",
            "severity": "warn",
            "alerts": 1,
            "uptime_cls": _class_for_uptime(84.1),
            "defect_cls": _class_for_defect(7.8),
        },
        {
            "name": "Mig24",
            "version": "v1.3.0",
            "status": "error",
            "uptime": 72.3,
            "defect_rate": 23.3,
            "last_inspection": "16 minutes ago",
            "severity": "critical",
            "alerts": 18,
            "uptime_cls": _class_for_uptime(72.3),
            "defect_cls": _class_for_defect(23.3),
        },
        {
            "name": "MDX",
            "version": "v1.3.0",
            "status": "online",
            "uptime": 92.3,
            "defect_rate": 5.3,
            "last_inspection": "14 minutes ago",
            "severity": "ok",
            "alerts": 0,
            "uptime_cls": _class_for_uptime(92.3),
            "defect_cls": _class_for_defect(5.3),
        },
    ]

    # live panel KPIs (active line)
    throughput: int = 0            # units/hour
    quality_pass: float = 87.6     # %
    uptime_today: float = 72.3     # %
    efficiency_oee: float = 87.2   # %

    # alerts (active line)
    alerts: List[Dict[str, str]] = [
        {"icon": "video-off",     "title": "Camera feed disconnected",           "time": "30 seconds ago", "level": "warn"},
        {"icon": "circle-alert",  "title": "Defect rate exceeded 10% threshold", "time": "1 minute ago",   "level": "warn"},
    ]

    # defect types (active line)
    defects: List[Dict[str, Union[str, int]]] = [
        {"type": "Surface Scratch", "count": 42},
        {"type": "Dent / Ding",     "count": 38},
        {"type": "Paint Defect",    "count": 31},
        {"type": "Misalignment",    "count": 26},
        {"type": "Crack / Break",   "count": 18},
        {"type": "Other",           "count": 12},
    ]

    # resolution time trend (active line)
    trend: List[Dict[str, float]] = [
        {"w": "W1", "actual": 5.1, "target": 4.5},
        {"w": "W2", "actual": 4.8, "target": 4.5},
        {"w": "W3", "actual": 5.6, "target": 4.5},
        {"w": "W4", "actual": 5.0, "target": 4.5},
        {"w": "W5", "actual": 4.6, "target": 4.5},
        {"w": "W6", "actual": 4.3, "target": 4.5},
    ]

    # ── Derived ─────────────────────────────────────────────
    @rx.var
    def alerts_count(self) -> int:
        return len(self.alerts)

    @rx.var
    def defects_pct(self) -> List[Dict[str, Union[str, float, int]]]:
        if not self.defects:
            return []
        max_c = max(int(d["count"]) for d in self.defects)
        out: List[Dict[str, Union[str, float, int]]] = []
        for d in self.defects:
            c = int(d["count"])
            pct = (c / max_c) * 100.0 if max_c > 0 else 0.0
            out.append({"type": str(d["type"]), "count": c, "pct": pct})
        return out

    @rx.var
    def lines_with_index(self) -> List[Dict[str, Union[str, float, int]]]:
        return [dict(item, idx=i) for i, item in enumerate(self.lines)]

    @rx.var
    def current_line_name(self) -> str:
        if not self.lines:
            return "—"
        idx = max(0, min(self.selected_idx, len(self.lines) - 1))
        return str(self.lines[idx]["name"])
    
    @rx.var
    def defects_legend(self) -> List[Dict[str, Union[str, int, float]]]:
        total = sum(int(d["count"]) for d in self.defects) or 1
        out: List[Dict[str, Union[str, int, float]]] = []
        for d in self.defects:
            c = int(d["count"])
            pct = round((c / total) * 100.0, 1)
            out.append({"type": str(d["type"]), "count": c, "pct": pct, "fill": str(d.get("fill", "#999"))})
        # sort desc by count so the biggest items sit on top
        out.sort(key=lambda x: int(x["count"]), reverse=True)
        return out

    # ── Events ─────────────────────────────────────────────
    def toggle_refresh(self): self.auto_refresh = not self.auto_refresh
    def toggle_live(self):    self.live_indicator = not self.live_indicator

    def select_line(self, idx: int):
        """Select a top card and repopulate the live panel with fresh dummy data."""
        if not (0 <= idx < len(self.lines)):
            return
        self.selected_idx = idx

        r = random.Random()  # new values each time
        # KPIs
        self.throughput   = r.randint(0, 60)
        self.quality_pass = round(r.uniform(78, 99), 1)
        self.uptime_today = round(r.uniform(65, 99), 1)
        self.efficiency_oee = round(r.uniform(70, 95), 1)

        # Alerts — 1–3 items chosen from a small set
        alert_pool = [
            {"icon": "video-off",     "title": "Camera feed disconnected",           "time": "30 seconds ago", "level": "warn"},
            {"icon": "circle-alert",  "title": "Defect rate exceeded 10% threshold", "time": "1 minute ago",   "level": "warn"},
            {"icon": "alert-triangle","title": "Anomaly detected by model",          "time": "2 minutes ago",  "level": "warn"},
            {"icon": "bell",          "title": "Scheduled maintenance reminder",     "time": "5 minutes ago",  "level": "warn"},
        ]
        k = r.randint(1, 3)
        self.alerts = [alert_pool[r.randrange(len(alert_pool))] for _ in range(k)]

        # Defect bars — keep types but randomize counts
        types = DEFECT_TYPES
        self.defects = [
            {"type": t, "count": r.randint(4, 45), "fill": PALETTE[i % len(PALETTE)]}
            for i, t in enumerate(types)
        ]

        # Trend — small wiggles around 4.8 with one high peak
        peaks = [round(r.uniform(4.4, 5.2), 1) for _ in range(6)]
        peaks[r.randrange(6)] = round(r.uniform(5.3, 5.7), 1)
        weeks = ["W1","W2","W3","W4","W5","W6"]
        self.trend = [{"w": w, "actual": v, "target": 4.5} for w, v in zip(weeks, peaks)]


# ────────────────────────── CSS ──────────────────────────
def _css() -> rx.Component:
    return rx.html(
        """
        <style>
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
          .lv-card.acc  { border-color:#c7b3ff; box-shadow:0 0 0 2px rgba(167,139,250,.25), 0 2px 6px rgba(2,6,23,.05); }
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
        """
    )


# ───────────────────── Small building blocks ─────────────────────
def _status_chip(status) -> rx.Component:
    label = rx.cond(status == "online", "Online", rx.cond(status == "idle", "Idle", "Error"))
    cls = rx.cond(
        status == "online", "lv-chip chip-online",
        rx.cond(status == "idle", "lv-chip chip-idle", "lv-chip chip-error"),
    )
    return rx.text(rx.fragment(rx.icon("dot", size=14), rx.text(label, as_="span")), class_name=cls)


def _severity_pill(sev):
    label = rx.cond(sev == "ok", "Pass", rx.cond(sev == "warn", "Warning", "Critical"))
    cls = rx.cond(sev == "ok", "pill pill-ok", rx.cond(sev == "warn", "pill pill-warn", "pill pill-critical"))
    return rx.text(label, class_name=cls)


def _percent_pill(val, pill_cls) -> rx.Component:
    return rx.text(rx.fragment(rx.text(val, as_="span"), rx.text("%", as_="span")), class_name=pill_cls)


def _top_line_card(item) -> rx.Component:
    card_cls = rx.cond(
        item["idx"] == PlantViewState.selected_idx, "lv-card snap selectable sel",
        rx.cond(item["severity"] == "critical", "lv-card snap selectable acc", "lv-card snap selectable"),
    )
    return rx.box(
        rx.box(
            rx.hstack(
                rx.text(item["name"], class_name="lv-line-name"),
                rx.text(item["version"], class_name="lv-line-ver"),
                rx.spacer(),
                _status_chip(item["status"]),
                align="center",
            ),
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
            rx.hstack(
                rx.text("Inspection", class_name="lv-sub"),
                rx.text(item["last_inspection"], class_name="lv-line-name"),
                class_name="lv-card-pad",
            ),
            rx.box(
                rx.text(rx.fragment(rx.text("Status ", as_="span", class_name="lv-sub"), _severity_pill(item["severity"]))),
                rx.text(
                    rx.fragment(
                        rx.text("Alerts ", as_="span", class_name="lv-sub"),
                        rx.text(item["alerts"], as_="span", class_name="lv-line-name"),
                    )
                ),
                class_name="lv-meta lv-card-pad",
            ),
            class_name="lv-line lv-card-pad",
        ),
        class_name=card_cls,
        on_click=lambda: PlantViewState.select_line(item["idx"]),
        min_width="300px",  
    )


def _top_cards() -> rx.Component:
    return rx.box(rx.foreach(PlantViewState.lines_with_index, _top_line_card), class_name="lv-top-strip")


def _kpi(title: str, value_node: rx.Component, sub: str) -> rx.Component:
    return rx.box(rx.text(title, class_name="label"), value_node, rx.text(sub, class_name="sub"), class_name="lv-kpi")

def _kpi_value_plain(v): return rx.text(v, class_name="value")
def _kpi_value_pct(v):   return rx.hstack(rx.text(v, class_name="value"), rx.text("%", as_="span", class_name="value"), align="center", spacing="1")


def _live_panel() -> rx.Component:
    feed = rx.box(
        rx.text("Defect Detected", class_name="lv-feed-badge"),
        rx.text("14:02:23 PM", class_name="lv-feed-clock"),
        rx.box(rx.icon("video", size=36), rx.text("Live Camera Feed", weight="bold"), rx.text("1920x1080 • 30fps", class_name="lv-sub"), class_name="lv-feed-watermark"),
        class_name="lv-feed",
    )
    kpis = rx.box(
        _kpi("Throughput", _kpi_value_plain(PlantViewState.throughput), "units/hour"),
        _kpi("Quality",     _kpi_value_pct(PlantViewState.quality_pass),   "pass rate"),
        _kpi("Uptime",      _kpi_value_pct(PlantViewState.uptime_today),   "today"),
        _kpi("Efficiency",  _kpi_value_pct(PlantViewState.efficiency_oee), "OEE"),
        class_name="lv-kpi-grid",
    )
    head = rx.hstack(
        rx.text(rx.fragment(rx.icon("activity"), rx.text(PlantViewState.current_line_name, as_="span")), class_name="lv-section-title"),
        rx.spacer(),
        rx.text(
            rx.fragment(rx.text("Live Feed", as_="span"), rx.box(class_name=rx.cond(PlantViewState.live_indicator, "lv-dot", "lv-dot off"))),
            class_name="lv-chip lv-chip-toggle",
            on_click=PlantViewState.toggle_live,
        ),
        align="center",
    )
    return rx.box(rx.box(head, class_name="lv-card-pad"), rx.box(feed, class_name="lv-pad"), rx.box(kpis, class_name="lv-pad"), class_name="lv-card")


def _actions_panel() -> rx.Component:
    return rx.box(
        rx.hstack(rx.icon("settings"), rx.text(" Actions", as_="span", weight="medium"), class_name="lv-card-pad"),
        rx.box(
            rx.button(rx.icon("rotate-cw"), "Recalibrate",         class_name="btn"),
            rx.button(rx.icon("download"),  "Download CSV",        class_name="btn"),
            rx.button(rx.icon("images"),    "Export Media",        class_name="btn"),
            rx.button(rx.icon("wrench"),    "Trigger Maintenance", class_name="btn danger"),
            class_name="lv-card-pad lv-actions",
        ),
        class_name="lv-card lv-actions-panel",
    )


def _alerts_panel() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.icon("sirens"),
            rx.text(
                rx.fragment(
                    rx.text("Live Alerts (", as_="span"),
                    rx.text(PlantViewState.alerts_count, as_="span"),
                    rx.text(")", as_="span"),
                ),
                as_="span",
                weight="medium",
            ),
            class_name="lv-card-pad",
        ),
        rx.box(
            rx.foreach(
                PlantViewState.alerts,
                lambda a: rx.box(
                    rx.icon(a["icon"], color="#ef4444"),
                    rx.box(rx.text(a["title"], class_name="lv-alert-title"), rx.text(a["time"], class_name="lv-alert-time")),
                    class_name="lv-alert-item",
                ),
            ),
            class_name="lv-card-pad lv-alerts-list",
        ),
        class_name="lv-card lv-actions-panel",
    )

def _defect_bars() -> rx.Component:
    pie = rx.recharts.pie_chart(
        rx.recharts.tooltip(),
        rx.recharts.pie(
            data=PlantViewState.defects,
            data_key="count",
            name_key="type",
            label=True,
            inner_radius=40,
            outer_radius=110,
            stroke="#ffffff",
            stroke_width=1,
        ),
        width="100%",
        height=300,
    )

    def legend_item(item):
        # one row with color swatch, name, and "count • pct%"
        return rx.box(
            rx.box(class_name="lv-legend-swatch", style={"background": item["fill"]}),
            rx.box(
                rx.text(item["type"], class_name="lv-legend-name"),
                rx.text(rx.fragment(
                    rx.text(item["count"], as_="span"),
                    rx.text(" • ", as_="span"),
                    rx.text(item["pct"], as_="span"),
                    rx.text("%", as_="span"),
                ), class_name="lv-legend-sub"),
                class_name="lv-legend-texts",
            ),
            class_name="lv-legend-item",
        )

    legend = rx.box(
        rx.foreach(PlantViewState.defects_legend, legend_item),
        class_name="lv-legend-wrap",
    )

    # Lay them out side-by-side on desktop, stacked on mobile.
    body = rx.box(
        rx.box(pie),
        rx.box(legend),
        class_name="lv-defect-grid",
    )

    return rx.box(
        rx.box(
            rx.hstack(
                rx.icon("pie-chart"),
                rx.text(" Defect Breakdown", as_="span", weight="medium"),
                align="center",
                padding="12px",
            ),
        ),
        rx.box(body, class_name="lv-pad"),
        class_name="lv-card",
    )

def _resolution_trend() -> rx.Component:
    return rx.box(
        rx.box(
            rx.hstack(
                rx.icon("trending-up"),
                rx.text(" Resolution Time Trend", as_="span", weight="medium"),
                align="center",
                padding="12px",
            ),
        ),
        rx.box(
            rx.recharts.line_chart(
                rx.recharts.cartesian_grid(stroke_dasharray="3 3"),
                rx.recharts.x_axis(data_key="w"),
                rx.recharts.y_axis(domain=[3.8, 5.8]),
                rx.recharts.tooltip(),
                rx.recharts.legend(),
                rx.recharts.line(type_="monotone", data_key="actual", stroke="#2563eb", dot={"r": 3, "fill": "#ffffff", "stroke": "#2563eb"}, stroke_width=2),
                rx.recharts.line(type_="monotone", data_key="target", stroke="#94a3b8", stroke_dasharray="6 4", dot=False, stroke_width=2),
                data=PlantViewState.trend,  # type: ignore
                width="100%", height=260, margin={"top": 6, "right": 12, "left": 0, "bottom": 4},
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
            ),
            align="center",
            gap="8px",
        ),
        class_name="lv-header",
    )

    top = rx.fragment(_top_cards(), rx.box(class_name="lv-top-hr"))

    main = rx.box(
        rx.box(_live_panel()),
        rx.box(rx.vstack(_actions_panel(), _alerts_panel(), gap="14px")),
        class_name="lv-grid-main",
    )

    bottom = rx.box(_defect_bars(), _resolution_trend(), class_name="lv-grid-bottom")

    return rx.box(
        _css(),
        rx.box(header, top, main, bottom, class_name="lv-page"),
        class_name="lv-shell",
        on_mount=PlantViewState.select_line(0),  # ensure KPIs populate on first load
    )
