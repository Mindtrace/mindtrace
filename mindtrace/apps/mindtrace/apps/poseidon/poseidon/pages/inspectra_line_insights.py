# pages/inspectra_line_insights.py
import random
import reflex as rx
from typing import List, Dict, Literal, Union

# ────────────────────────── Helpers / Palette ──────────────────────────
PALETTE = [
    "#2563eb",  # blue
    "#16a34a",  # green
    "#f59e0b",  # amber
    "#ef4444",  # red
    "#7c3aed",  # violet
    "#06b6d4",  # cyan
    "#111827",  # slate-900
    "#94a3b8",  # slate-400
]

DefectKind = Literal[
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
Granularity = Literal["Hourly", "Daily", "Weekly"]

DEFECT_TYPES: List[DefectKind] = [
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

SHIFTS = ["S1", "S2", "S3"]  # Shift 1/2/3 (legend labels set below)

SHIFT_COLORS = {
    "S1": PALETTE[0],  # blue
    "S2": PALETTE[1],  # green
    "S3": PALETTE[2],  # amber
}


def _css() -> rx.Component:
    return rx.html(
        """
        <style>
          .ai-shell { display:flex; justify-content:center; padding:24px; background:#f5f7fb; }
          .ai-page  { width:min(1200px, 100%); display:flex; flex-direction:column; gap:16px; }

          .ai-header { display:flex; justify-content:space-between; align-items:center; }
          .ai-title  { font-size:1.35rem; font-weight:800; color:#111827; }
          .ai-sub    { color:#6b7280; }
          .ai-actions { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }

          .ai-select, .ai-button {
            border:1px solid rgba(17,24,39,.12);
            background:#fff; border-radius:10px; padding:8px 10px; font-weight:600; color:#111827;
          }
          .ai-button:hover { background:#f3f4f6; }
          .ai-chip { padding:4px 10px; border-radius:999px; border:1px solid rgba(17,24,39,.12); background:#fff; font-weight:700; font-size:.82rem; }
          .ai-chip.toggle { cursor:pointer; }
          .ai-dot { width:8px; height:8px; border-radius:999px; background:#22c55e; display:inline-block; }
          .ai-dot.off { background:#9ca3af; }

          .ai-grid { display:grid; gap:16px; }
          .ai-grid.two { grid-template-columns: 1fr 1fr; }
          .ai-card { background:#fff; border:1px solid rgba(17,24,39,.08); border-radius:14px; box-shadow:0 2px 6px rgba(2,6,23,.05); }
          .ai-card-pad { padding:14px; }
          .ai-card-title { display:flex; align-items:center; gap:8px; font-weight:800; color:#111827; }

          .ai-row { display:flex; justify-content:space-between; align-items:center; gap:10px; }
          .ai-muted { color:#6b7280; }

          /* Big legend for many defect types */
          .ai-defect-grid { display:grid; grid-template-columns: 1.1fr 1fr; gap:12px; align-items:start; }
          @media (max-width: 920px) { .ai-defect-grid { grid-template-columns: 1fr; } }

          .ai-legend-wrap { display:grid; grid-template-columns: 1fr 1fr; gap:8px 14px; max-height:260px; overflow:auto; padding-right:6px; }
          .ai-legend-item { display:flex; align-items:center; gap:10px; min-width:0; }
          .ai-legend-swatch { width:12px; height:12px; border-radius:3px; flex:0 0 auto; box-shadow: inset 0 0 0 1px rgba(0,0,0,.08); }
          .ai-legend-texts { display:flex; flex-direction:column; gap:2px; min-width:0; }
          .ai-legend-name { color:#111827; font-weight:600; font-size:.86rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
          .ai-legend-sub  { color:#6b7280; font-size:.78rem; }

          /* Chat panel */
          .ai-chat { display:flex; flex-direction:column; gap:10px; height:300px; }
          .ai-chat-feed {
            flex:1; overflow:auto; padding:8px; border:1px solid rgba(17,24,39,.08);
            border-radius:10px; background:#fff;
          }
          .ai-chat-input { display:flex; gap:8px; }
          .ai-msg { display:flex; margin-bottom:8px; }
          .ai-msg.assistant { justify-content:flex-start; }
          .ai-msg.user { justify-content:flex-end; }
          .ai-bubble {
            max-width:80%; padding:8px 10px; border-radius:12px; box-shadow:0 1px 2px rgba(2,6,23,.05);
            font-size:.92rem; line-height:1.25;
          }
          .ai-bubble.assistant { background:#eef2f7; color:#111827; border:1px solid rgba(17,24,39,.08); }
          .ai-bubble.user { background:#2563eb; color:#fff; }

          .ai-chat-empty {
            flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center;
            gap:12px; border:1px dashed rgba(17,24,39,.15); border-radius:10px; background:#fff; padding:16px;
            text-align:center;
          }
          .ai-chat-empty h4 { margin:0; font-weight:800; color:#111827; }
          .ai-chat-empty p  { margin:0; color:#6b7280; font-size:.9rem; }
          .ai-samples { display:flex; flex-wrap:wrap; gap:8px; justify-content:center; }
          .ai-chip-btn { border:1px solid rgba(17,24,39,.12); background:#f8fafc; padding:6px 10px; border-radius:999px; font-weight:600; cursor:pointer; color:#111827; }
          .ai-chip-btn:hover { background:#eef2f7; }
        </style>
        """
    )


# ────────────────────────── State ──────────────────────────
class InspectraLineInsightsState(rx.State):
    """Dummy-but-dynamic data for the Inspectra Line Insights page."""

    # Global controls
    auto_refresh: bool = True
    granularity: Granularity = "Hourly"   # drives ALL analytics
    defect_filter: str = "All Defects"    # ← now supports "All Defects"
    overview_filter: str = "All"

    # ── Defect trends (single-series; used by chat calcs) ──
    defect_trends_hourly: Dict[str, List[Dict[str, Union[str, int]]]] = {}
    defect_trends_daily: Dict[str, List[Dict[str, Union[str, int]]]] = {}
    defect_trends_weekly: Dict[str, List[Dict[str, Union[str, int]]]] = {}

    # ── Shifted multi-bar defect trends (S1/S2/S3) ─────────
    defect_trends_shift_hourly: Dict[str, List[Dict[str, Union[str, int]]]] = {}
    defect_trends_shift_daily: Dict[str, List[Dict[str, Union[str, int]]]] = {}
    defect_trends_shift_weekly: Dict[str, List[Dict[str, Union[str, int]]]] = {}

    # ── Donut/pie mixes per granularity (so it updates!) ───
    defects_hourly: List[Dict[str, Union[str, int]]] = []
    defects_daily: List[Dict[str, Union[str, int]]] = []
    defects_weekly: List[Dict[str, Union[str, int]]] = []

    # AI donut (static %s – we nudge them)
    ai_trends: Dict[str, int] = {"AI Correct": 72, "False Positive": 18, "False Negative": 10}

    # Performance series per granularity
    performance_hourly: List[Dict[str, Union[str, float]]] = []
    performance_daily: List[Dict[str, Union[str, float]]] = []
    performance_weekly: List[Dict[str, Union[str, float]]] = []

    # Avg Yield bars per granularity
    uptime_hourly_24: List[Dict[str, Union[str, float]]] = []  # 24 bars H1..H24
    uptime_7d: List[Dict[str, Union[str, float]]] = []         # 7 days
    uptime_8w: List[Dict[str, Union[str, float]]] = []         # 8 weeks

    # Chat
    messages: List[Dict[str, str]] = []
    input_text: str = ""
    
    shift_filter: str = "All"  # "All", "S1", "S2", or "S3"

    @rx.event
    def set_shift_filter(self, v: str):
        self.shift_filter = v or "All"

    # ── Chat events ─────────────────────────────────────────
    @rx.event
    def set_input(self, v: str):
        self.input_text = v

    @rx.event
    def send_message(self):
        q = (self.input_text or "").strip()
        if not q:
            return
        self.messages = [*self.messages, {"role": "user", "text": q}]
        series = self.current_defect_series  # single-series (count)
        total = sum(int(pt["count"]) for pt in series) or 1
        avg = total / (len(series) or 1)
        reply = (
            f"For '{self.defect_filter}' ({self.granularity.lower()}), avg count is ~{avg:.2f}. "
            "Mid-cycle tends to spike; consider scheduling focused inspections then."
        )
        self.messages = [*self.messages, {"role": "assistant", "text": reply}]
        self.input_text = ""

    # ── Seeding ────────────────────────────────────────────
    def _seed(self):
        r = random.Random(42)

        # Labels per granularity
        hours = [f"H{i}" for i in range(1, 25)]
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        weeks = [f"W-{i}" for i in range(7, -1, -1)]  # W-7 .. W-0 (current)

        # base single-series per defect
        def _def_series(label_list, base_offset):
            out = []
            for i, lab in enumerate(label_list):
                base = base_offset + (i % 4)
                jitter = r.randint(0, 6)
                bump = 4 if (i % 5 == 2) else 0
                out.append({"x": lab, "count": base + jitter + bump})
            return out

        # shifted multi-series per defect
        def _def_series_shift(label_list, base_offset):
            out = []
            for i, lab in enumerate(label_list):
                base = base_offset + (i % 4)
                # randomize shifts but keep them in a reasonable total band
                s1 = max(0, base + r.randint(0, 5))
                s2 = max(0, base + r.randint(0, 5))
                s3 = max(0, base + r.randint(0, 5))
                # occasional bump on the middle of cycle
                if i % 5 == 2:
                    s2 += 3
                out.append({"x": lab, "S1": s1, "S2": s2, "S3": s3})
            return out

        # Seed maps for each granularity
        self.defect_trends_hourly = {d: _def_series(hours, 4 + (i % 3)) for i, d in enumerate(DEFECT_TYPES)}
        self.defect_trends_daily = {d: _def_series(days, 6 + (i % 5)) for i, d in enumerate(DEFECT_TYPES)}
        self.defect_trends_weekly = {d: _def_series(weeks, 22 + (i % 4)) for i, d in enumerate(DEFECT_TYPES)}

        self.defect_trends_shift_hourly = {d: _def_series_shift(hours, 4 + (i % 3)) for i, d in enumerate(DEFECT_TYPES)}
        self.defect_trends_shift_daily = {d: _def_series_shift(days, 6 + (i % 5)) for i, d in enumerate(DEFECT_TYPES)}
        self.defect_trends_shift_weekly = {d: _def_series_shift(weeks, 22 + (i % 4)) for i, d in enumerate(DEFECT_TYPES)}

        # Donut mixes per granularity (distinct distributions)
        def _mix(base: int, jitter: int) -> List[Dict[str, Union[str, int]]]:
            out = []
            for i, t in enumerate(DEFECT_TYPES):
                count = max(1, base + (i % 7) + r.randint(0, jitter))
                out.append({"type": t, "count": count, "fill": PALETTE[i % len(PALETTE)]})
            return out

        self.defects_hourly = _mix(6, 8)    # more noisy, short-term
        self.defects_daily = _mix(10, 10)   # moderate
        self.defects_weekly = _mix(16, 12)  # smoother but higher totals

        # AI Trends donut (seeded)
        self.ai_trends = {"AI Correct": 72, "False Positive": 18, "False Negative": 10}

        # Performance series
        def _perf_rows(labels, up_base, up_jit, dr_base, dr_jit):
            rows = []
            for lab in labels:
                rows.append({
                    "t": lab,
                    "Avg Yield": round(max(0, min(100, r.uniform(up_base - up_jit, up_base + up_jit))), 2),
                    "Defect Rate": round(max(0, min(100, r.uniform(dr_base - dr_jit, dr_base + dr_jit))), 2),
                })
            return rows

        self.performance_hourly = _perf_rows(hours, 92, 5, 8, 3)
        self.performance_daily = _perf_rows(days, 90, 6, 7, 2.5)
        self.performance_weekly = _perf_rows(weeks, 88, 7, 6, 2)

        # Avg Yield bars per granularity
        def _uptime(labels, base, jit):
            return [{"x": lab, "uptime": round(max(0, min(100, r.uniform(base - jit, base + jit))), 2)} for lab in labels]

        self.uptime_hourly_24 = _uptime(hours, 85, 10)
        self.uptime_7d = _uptime(days, 60, 20)
        self.uptime_8w = _uptime(weeks, 70, 12)

    # ── Derived vars ────────────────────────────────────────
    @rx.var
    def defect_trends_map(self) -> Dict[str, List[Dict[str, Union[str, int]]]]:
        return (
            self.defect_trends_hourly if self.granularity == "Hourly"
            else self.defect_trends_daily if self.granularity == "Daily"
            else self.defect_trends_weekly
        )

    @rx.var
    def defect_trends_shift_map(self) -> Dict[str, List[Dict[str, Union[str, int]]]]:
        return (
            self.defect_trends_shift_hourly if self.granularity == "Hourly"
            else self.defect_trends_shift_daily if self.granularity == "Daily"
            else self.defect_trends_shift_weekly
        )

    @rx.var
    def current_defect_series(self) -> List[Dict[str, Union[str, int]]]:
        """Single-series (count) for chat and simple analytics."""
        # Pick the correct single-series defect map based on granularity
        active = (
            self.defect_trends_hourly
            if self.granularity == "Hourly"
            else self.defect_trends_daily
            if self.granularity == "Daily"
            else self.defect_trends_weekly
        )

        if not active:
            return []

        # Aggregate across all defects if "All Defects" selected
        if self.defect_filter == "All Defects":
            any_defect = next(iter(active.keys()))
            template = [{"x": row["x"], "count": 0} for row in active[any_defect]]
            for rows in active.values():
                for i, row in enumerate(rows):
                    template[i]["count"] += int(row["count"])
            return template

        return active.get(self.defect_filter, [])


    @rx.var
    def current_defect_series_shift(self) -> List[Dict[str, Union[str, int]]]:
        """Multi-bar (S1/S2/S3). Aggregates across defects and filters by shift."""
        active = self.defect_trends_shift_map
        if not active:
            return []

        # ── Aggregate across all defects if "All Defects" selected ──
        if self.defect_filter == "All Defects":
            any_defect = next(iter(active.keys()))
            template = [{"x": row["x"], "S1": 0, "S2": 0, "S3": 0} for row in active[any_defect]]
            for rows in active.values():
                for i, row in enumerate(rows):
                    template[i]["S1"] += int(row["S1"])
                    template[i]["S2"] += int(row["S2"])
                    template[i]["S3"] += int(row["S3"])
        else:
            template = active.get(self.defect_filter, [])

        # ── Apply shift filter dynamically ──
        if self.shift_filter == "All":
            return template
        else:
            key = self.shift_filter
            return [{"x": row["x"], key: row.get(key, 0)} for row in template]


    @rx.var
    def performance_series(self) -> List[Dict[str, Union[str, float]]]:
        if self.granularity == "Hourly":
            return self.performance_hourly
        if self.granularity == "Daily":
            return self.performance_daily
        return self.performance_weekly

    @rx.var
    def uptime_series(self) -> List[Dict[str, Union[str, float]]]:
        if self.granularity == "Hourly":
            return self.uptime_hourly_24
        if self.granularity == "Daily":
            return self.uptime_7d
        return self.uptime_8w

    @rx.var
    def defects_current(self) -> List[Dict[str, Union[str, int]]]:
        """Pie data that tracks granularity."""
        if self.granularity == "Hourly":
            return self.defects_hourly
        if self.granularity == "Daily":
            return self.defects_daily
        return self.defects_weekly

    @rx.var
    def defects_legend(self) -> List[Dict[str, Union[str, int, float]]]:
        data = self.defects_current
        total = sum(int(d["count"]) for d in data) or 1
        out: List[Dict[str, Union[str, int, float]]] = []
        for i, d in enumerate(data):
            c = int(d["count"])
            pct = round((c / total) * 100.0, 1)
            out.append({
                "type": str(d["type"]),
                "count": c,
                "pct": pct,
                "fill": str(d.get("fill", PALETTE[i % len(PALETTE)])),
            })
        out.sort(key=lambda x: int(x["count"]), reverse=True)
        return out

    # ── Lifecycle ───────────────────────────────────────────
    def on_mount(self):
        self._seed()
        self.refresh_tick()

    # ── Refresh (nudges whichever series are currently active) ─────────
    def refresh_tick(self):
        if not self.auto_refresh:
            return
        r = random.Random()

        # Defects single-series (for chat calc)
        for v in self.current_defect_series:
            v["count"] = max(0, int(v["count"]) + r.randint(-2, 2))

        # Defects multi-series (shifts)
        for row in self.current_defect_series_shift:
            row["S1"] = max(0, int(row["S1"]) + r.randint(-1, 2))
            row["S2"] = max(0, int(row["S2"]) + r.randint(-1, 2))
            row["S3"] = max(0, int(row["S3"]) + r.randint(-1, 2))

        # AI donut (normalize)
        c = max(0, self.ai_trends["AI Correct"] + r.randint(-2, 2))
        fp = max(0, self.ai_trends["False Positive"] + r.randint(-2, 2))
        fn = max(0, self.ai_trends["False Negative"] + r.randint(-2, 2))
        total = c + fp + fn or 1
        c = int(round(c / total * 100))
        fp = int(round(fp / total * 100))
        fn = max(0, 100 - c - fp)
        self.ai_trends = {"AI Correct": c, "False Positive": fp, "False Negative": fn}

        # Performance (active)
        for p in self.performance_series:
            p["Avg Yield"] = round(max(0, min(100, float(p["Avg Yield"]) + r.uniform(-2.5, 2.5))), 2)
            p["Defect Rate"] = round(max(0, min(100, float(p["Defect Rate"]) + r.uniform(-1.2, 1.2))), 2)

        # Avg Yield bars (active)
        for b in self.uptime_series:
            b["uptime"] = round(max(0, min(100, float(b["uptime"]) + r.uniform(-3.0, 3.0))), 2)

        # Pie counts (active granularity mix)
        for i, d in enumerate(self.defects_current):
            d["count"] = max(0, int(d["count"]) + r.randint(-2, 2))
            d["fill"] = d.get("fill", PALETTE[i % len(PALETTE)])

    # ── Event handlers ──────────────────────────────────────
    @rx.event
    def set_overview_filter(self, v: str):
        self.overview_filter = v

    @rx.event
    def set_defect_filter(self, v: str):
        self.defect_filter = v

    @rx.event
    def set_granularity(self, v: Granularity):
        self.granularity = v  # data & charts react via derived vars

    @rx.event
    def toggle_refresh(self):
        self.auto_refresh = not self.auto_refresh

    @rx.var
    def has_messages(self) -> bool:
        return len(self.messages) > 0

    @rx.event
    def quick_ask(self, text: str):
        self.input_text = text
        self.send_message()

    @rx.event
    def clear_chat(self):
        self.messages = []
        self.input_text = ""


# ────────────────────────── Small UI helpers ──────────────────────────
def _card(title_icon: str, title, *children) -> rx.Component:
    """Generic card with icon + title inline."""
    # If title is not already a component, make it a text node
    title_comp = title if isinstance(title, rx.Component) else rx.text(str(title))

    return rx.box(
        # Header section
        rx.hstack(
            rx.icon(title_icon),
            title_comp,  # ✅ this supports rx.text or rx.fragment
            align="center",
            class_name="ai-card-title ai-card-pad",
            spacing="2",
        ),
        # Body section
        rx.box(*children, class_name="ai-card-pad"),
        class_name="ai-card",
    )



# ────────────────────────── Sections ──────────────────────────
def _header() -> rx.Component:
    # Global granularity select (prominent in header)
    granularity_select = rx.select(
        ["Hourly", "Daily", "Weekly"],
        value=InspectraLineInsightsState.granularity,
        on_change=InspectraLineInsightsState.set_granularity,
        class_name="ai-select",
        title="Change granularity for ALL analytics",
    )

    return rx.box(
        rx.box(
            rx.text("Line Insights", class_name="ai-title"),
            rx.text("Strategic analysis and trends from inspection data", class_name="ai-sub"),
        ),
        rx.hstack(
            granularity_select,
            rx.button(
                rx.icon("rotate-cw"),
                rx.text(" Refresh Now", as_="span"),
                class_name="ai-button",
                on_click=InspectraLineInsightsState.refresh_tick,
                title="Nudge live data",
            ),
            rx.box(
                rx.text("Auto Refresh", as_="span", class_name="ai-muted", margin_right="6px"),
                rx.box(class_name=rx.cond(InspectraLineInsightsState.auto_refresh, "ai-dot", "ai-dot off")),
                class_name="ai-chip toggle",
                on_click=InspectraLineInsightsState.toggle_refresh,
                title="Toggle Auto Refresh",
            ),
            align="center",
            class_name="ai-actions",
        ),
        class_name="ai-header",
    )


def _overview_row() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.icon("eye"),
            rx.text("Overview", weight="bold"),
        ),
        class_name="ai-row",
    )


def _defect_trends() -> rx.Component:
    defect_selector = rx.select(
        ["All Defects", *DEFECT_TYPES],
        value=InspectraLineInsightsState.defect_filter,
        on_change=InspectraLineInsightsState.set_defect_filter,
        class_name="ai-select",
        title="Choose defect type (or All Defects)",
    )

    shift_selector = rx.select(
        ["All", "S1", "S2", "S3"],
        value=InspectraLineInsightsState.shift_filter,
        on_change=InspectraLineInsightsState.set_shift_filter,
        class_name="ai-select",
        title="Filter by production shift",
    )

    header = rx.box(
        rx.hstack(
            rx.hstack(rx.icon("bar-chart-2"), rx.text(" Defect Trends by Shift", as_="span"), align="center"),
            rx.spacer(),
            shift_selector,
            defect_selector,
            align="center",
            width="100%",
        ),
        class_name="ai-card-title ai-card-pad",
    )

    # 🟦🟩🟧 dynamic legend based on selected shift
    legend = rx.cond(
        InspectraLineInsightsState.shift_filter == "All",
        rx.recharts.legend(
            payload=[
                {"value": "Shift 1", "type": "square", "color": SHIFT_COLORS["S1"]},
                {"value": "Shift 2", "type": "square", "color": SHIFT_COLORS["S2"]},
                {"value": "Shift 3", "type": "square", "color": SHIFT_COLORS["S3"]},
            ]
        ),
        rx.recharts.legend(
            payload=[
                {
                    "value": rx.cond(
                        InspectraLineInsightsState.shift_filter == "S1",
                        "Shift 1",
                        rx.cond(
                            InspectraLineInsightsState.shift_filter == "S2",
                            "Shift 2",
                            "Shift 3",
                        ),
                    ),
                    "type": "square",
                    "color": rx.cond(
                        InspectraLineInsightsState.shift_filter == "S1",
                        SHIFT_COLORS["S1"],
                        rx.cond(
                            InspectraLineInsightsState.shift_filter == "S2",
                            SHIFT_COLORS["S2"],
                            SHIFT_COLORS["S3"],
                        ),
                    ),
                }
            ]
        ),
    )

    # 📊 Chart
    bars = rx.recharts.bar_chart(
        rx.recharts.cartesian_grid(stroke_dasharray="3 3"),
        rx.recharts.x_axis(data_key="x"),
        rx.recharts.y_axis(),
        rx.recharts.tooltip(),
        legend,

        # 🟦 Shift 1 bar — dims when not selected
        rx.recharts.bar(
            data_key="S1",
            stroke=SHIFT_COLORS["S1"],
            fill=rx.cond(
                InspectraLineInsightsState.shift_filter == "All",
                SHIFT_COLORS["S1"],
                rx.cond(
                    InspectraLineInsightsState.shift_filter == "S1",
                    SHIFT_COLORS["S1"],
                    "#e5e7eb",  # muted gray when inactive
                ),
            ),
            fill_opacity=rx.cond(
                InspectraLineInsightsState.shift_filter == "All",
                1,
                rx.cond(
                    InspectraLineInsightsState.shift_filter == "S1",
                    1,
                    0.35,  # fade others
                ),
            ),
        ),

        # 🟩 Shift 2 bar
        rx.recharts.bar(
            data_key="S2",
            stroke=SHIFT_COLORS["S2"],
            fill=rx.cond(
                InspectraLineInsightsState.shift_filter == "All",
                SHIFT_COLORS["S2"],
                rx.cond(
                    InspectraLineInsightsState.shift_filter == "S2",
                    SHIFT_COLORS["S2"],
                    "#e5e7eb",
                ),
            ),
            fill_opacity=rx.cond(
                InspectraLineInsightsState.shift_filter == "All",
                1,
                rx.cond(
                    InspectraLineInsightsState.shift_filter == "S2",
                    1,
                    0.35,
                ),
            ),
        ),

        # 🟧 Shift 3 bar
        rx.recharts.bar(
            data_key="S3",
            stroke=SHIFT_COLORS["S3"],
            fill=rx.cond(
                InspectraLineInsightsState.shift_filter == "All",
                SHIFT_COLORS["S3"],
                rx.cond(
                    InspectraLineInsightsState.shift_filter == "S3",
                    SHIFT_COLORS["S3"],
                    "#e5e7eb",
                ),
            ),
            fill_opacity=rx.cond(
                InspectraLineInsightsState.shift_filter == "All",
                1,
                rx.cond(
                    InspectraLineInsightsState.shift_filter == "S3",
                    1,
                    0.35,
                ),
            ),
        ),

        data=InspectraLineInsightsState.current_defect_series_shift,
        width="100%",
        height=300,
    )


    return rx.box(
        header,
        rx.box(bars, class_name="ai-card-pad"),
        class_name="ai-card",
    )



def _chat_panel() -> rx.Component:
    def bubble(msg):
        role = msg["role"]
        bubble_cls = rx.cond(role == "user", "ai-bubble user", "ai-bubble assistant")
        row_cls = rx.cond(role == "user", "ai-msg user", "ai-msg assistant")
        return rx.box(rx.box(rx.text(msg["text"]), class_name=bubble_cls), class_name=row_cls)

    feed = rx.box(
        rx.foreach(InspectraLineInsightsState.messages, lambda m: bubble(m)),
        class_name="ai-chat-feed",
    )

    empty = rx.box(
        rx.icon("bot", size=28, color="#111827"),
        rx.html("<h4>How can I help?</h4>"),
        rx.html("<p>Try a prompt below to explore trends.</p>"),
        rx.box(
            rx.button(
                "Top 3 rising defects",
                class_name="ai-chip-btn",
                on_click=lambda: InspectraLineInsightsState.quick_ask(
                    "What are the top 3 rising defects this week?"
                ),
            ),
            rx.button(
                "Volatility: Weld Cracks",
                class_name="ai-chip-btn",
                on_click=lambda: InspectraLineInsightsState.quick_ask(
                    "Show volatility over time for Weld Cracks"
                ),
            ),
            rx.button(
                "Compare sites",
                class_name="ai-chip-btn",
                on_click=lambda: InspectraLineInsightsState.quick_ask(
                    "Compare defect rate trends for Lakewood vs Ramos"
                ),
            ),
            rx.button(
                "Peak times today",
                class_name="ai-chip-btn",
                on_click=lambda: InspectraLineInsightsState.quick_ask(
                    "When were peak defect times today?"
                ),
            ),
            class_name="ai-samples",
        ),
        class_name="ai-chat-empty",
    )

    input_row = rx.box(
        rx.input(
            placeholder='Ask about trends (e.g., "Show volatility for Weld Cracks").',
            value=InspectraLineInsightsState.input_text,
            on_change=InspectraLineInsightsState.set_input,
            class_name="ai-select",
            style={"flex": "1"},
        ),
        rx.button(
            rx.icon("send"),
            rx.text(" Send", as_="span"),
            class_name="ai-button",
            on_click=InspectraLineInsightsState.send_message,
        ),
        class_name="ai-chat-input",
    )

    new_chat_btn = rx.button(
        rx.icon("eraser"),
        rx.text(" New Chat", as_="span"),
        class_name="ai-button",
        on_click=InspectraLineInsightsState.clear_chat,
        title="Clear chat and start fresh",
    )

    header = rx.box(
        rx.hstack(
            rx.hstack(
                rx.icon("message-square"),
                rx.text(" Ask Inspectra", as_="span"),
                align="center",
            ),
            rx.spacer(),
            new_chat_btn,
            align="center",
            width="100%",
        ),
        class_name="ai-card-title ai-card-pad",
    )

    body = rx.box(
        rx.cond(InspectraLineInsightsState.has_messages, feed, empty),
        input_row,
        class_name="ai-chat",
    )

    return rx.box(
        header,
        rx.box(body, class_name="ai-card-pad"),
        class_name="ai-card",
    )


def _defect_breakdown() -> rx.Component:
    pie = rx.recharts.pie_chart(
        rx.recharts.tooltip(),
        rx.recharts.pie(
            data=InspectraLineInsightsState.defects_current,   # reactive to granularity
            data_key="count",
            name_key="type",
            label=True,
            inner_radius=45,
            outer_radius=110,
            stroke="#ffffff",
            stroke_width=1,
        ),
        width="100%",
        height=300,
    )

    def legend_item(item):
        return rx.box(
            rx.box(class_name="ai-legend-swatch", style={"background": item["fill"]}),
            rx.box(
                rx.text(item["type"], class_name="ai-legend-name"),
                rx.text(
                    rx.fragment(
                        rx.text(item["count"], as_="span"),
                        rx.text(" • ", as_="span"),
                        rx.text(item["pct"], as_="span"),
                        rx.text("%", as_="span"),
                    ),
                    class_name="ai-legend-sub",
                ),
                class_name="ai-legend-texts",
            ),
            class_name="ai-legend-item",
        )

    legend = rx.box(
        rx.foreach(InspectraLineInsightsState.defects_legend, legend_item),
        class_name="ai-legend-wrap",
    )

    body = rx.box(
        rx.box(pie),
        rx.box(legend),
        class_name="ai-defect-grid",
    )

    # ✅ Use rx.fragment for title (like performance_trends)
    title = rx.text(
        rx.fragment("Defect Breakdown (", InspectraLineInsightsState.granularity, ")"),
        weight="bold",
    )
    return _card("pie-chart", title, body)




def _performance_trends() -> rx.Component:
    chart = rx.recharts.line_chart(
        rx.recharts.cartesian_grid(stroke_dasharray="3 3"),
        rx.recharts.x_axis(data_key="t"),
        rx.recharts.y_axis(domain=[0, 100]),
        rx.recharts.tooltip(),
        rx.recharts.legend(),
        rx.recharts.line(type_="monotone", data_key="Avg Yield", stroke=PALETTE[0],
                         dot={"r": 3, "fill": "#fff", "stroke": PALETTE[0]}),
        rx.recharts.line(type_="monotone", data_key="Defect Rate", stroke=PALETTE[2],
                         dot={"r": 3, "fill": "#fff", "stroke": PALETTE[2]}),
        data=InspectraLineInsightsState.performance_series,  # type: ignore
        width="100%",
        height=260,
    )
    title = rx.text(
        rx.fragment("Performance Trends (", InspectraLineInsightsState.granularity, ")"),
        weight="bold",
    )
    return _card("activity", title, chart)


def _uptime_card() -> rx.Component:
    chart = rx.recharts.bar_chart(
        rx.recharts.cartesian_grid(stroke_dasharray="3 3"),
        rx.recharts.x_axis(data_key="x"),
        rx.recharts.y_axis(domain=[0, 100]),
        rx.recharts.tooltip(),
        rx.recharts.bar(data_key="uptime", radius=[4, 4, 0, 0], fill=PALETTE[0]),
        data=InspectraLineInsightsState.uptime_series, width="100%", height=260,
    )
    title = rx.text(
        rx.fragment("Avg Yield Trends (", InspectraLineInsightsState.granularity, ")"),
        weight="bold",
    )
    return _card("calendar", title, chart)


# ────────────────────────── Page ──────────────────────────
def inspectra_line_insights() -> rx.Component:
    return rx.box(
        _css(),
        rx.box(
            _header(),
            _overview_row(),

            rx.box(
                _defect_trends(),
                _chat_panel(),
                class_name="ai-grid two",
            ),

            rx.box(
                _performance_trends(),
                _uptime_card(),
                class_name="ai-grid two",
            ),

            _defect_breakdown(),

            class_name="ai-page",
        ),
        on_mount=InspectraLineInsightsState.on_mount,
        class_name="ai-shell",
    )
