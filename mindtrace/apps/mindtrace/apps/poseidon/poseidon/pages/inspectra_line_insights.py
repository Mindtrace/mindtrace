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

DefectKind = Literal["Discolouration", "Surface Scratches", "Cracks", "Dents"]
PerfGranularity = Literal["Hourly", "Daily"]
MetricKind = Literal["Yield", "Defect Rate", "Uptime"]

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

def _css() -> rx.Component:
    return rx.html(
        """
        <style>
          .ai-shell { display:flex; justify-content:center; padding:24px; background:#f5f7fb; }
          .ai-page  { width:min(1200px, 100%); display:flex; flex-direction:column; gap:16px; }

          .ai-header { display:flex; justify-content:space-between; align-items:center; }
          .ai-title  { font-size:1.35rem; font-weight:800; color:#111827; }
          .ai-sub    { color:#6b7280; }
          .ai-actions { display:flex; gap:8px; align-items:center; }

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
          .ai-legend-dot { display:inline-block; width:10px; height:10px; border-radius:999px; margin-right:6px; }

          .ai-row { display:flex; justify-content:space-between; align-items:center; gap:10px; }
          .ai-muted { color:#6b7280; }

          /* Tabs (button group) */
          .ai-tabs { display:flex; gap:8px; background:#eef2f7; padding:4px; border-radius:999px; }
          .ai-tab { border:none; background:transparent; padding:6px 10px; border-radius:999px; color:#334155; font-weight:600; cursor:pointer; }
          .ai-tab.active { background:#fff; box-shadow:0 1px 3px rgba(2,6,23,.08); color:#0f172a; }
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
    # Controls
    auto_refresh: bool = True
    DefectKind = str
    defect_filter: DefectKind = DEFECT_TYPES[0]
    perf_granularity: PerfGranularity = "Hourly"
    site_metric: MetricKind = "Yield"

    # Overview filter (visual only)
    overview_filter: str = "All"

    # Full defect list for the pie (name, count, color)
    defects: List[Dict[str, Union[str, int]]] = []

    # Data stores
    defect_trends: Dict[DefectKind, List[Dict[str, Union[str, int]]]] = {}
    ai_trends: Dict[str, int] = {"AI Correct": 72, "False Positive": 18, "False Negative": 10}
    performance_hourly: List[Dict[str, Union[str, float]]] = []
    performance_daily: List[Dict[str, Union[str, float]]] = []
    uptime_7d: List[Dict[str, Union[str, float]]] = []

    # Sites & site trends (LAKEWOOD / RAMOS / CLANTON)
    sites: List[str] = ["Lakewood", "Ramos", "Clanton"]
    site_trends: Dict[MetricKind, List[Dict[str, Union[str, float]]]] = {}
    
    # Chat
    messages: List[Dict[str, str]] = []
    input_text: str = ""

    @rx.event
    def set_input(self, v: str):
        self.input_text = v

    @rx.event
    def send_message(self):
        q = (self.input_text or "").strip()
        if not q:
            return
        # append user message
        self.messages = [*self.messages, {"role": "user", "text": q}]
        # dummy reply based on current selected defect
        series = self.defect_trends.get(self.defect_filter, [])
        total = sum(int(pt["count"]) for pt in series) or 1
        avg = total / (len(series) or 1)
        reply = (
            f"For '{self.defect_filter}', avg daily count is ~{avg:.2f}. "
            "Mid-week tends to spike; consider scheduling inspections Tue–Thu."
        )
        self.messages = [*self.messages, {"role": "assistant", "text": reply}]
        self.input_text = ""


    # ── Init / seed ─────────────────────────────────────────
    def _seed(self):
        r = random.Random(42)
        days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

        # Defect Trends (by type)
        self.defect_trends = {}
        for i, defect in enumerate(DEFECT_TYPES):
            series = []
            for d in days:
                base = 6 + (i % 6)            # distribute baselines a bit by index
                jitter = r.randint(0, 12)     # variability
                bump = 6 if (d == "Wed" and i % 3 == 0) else 0  # occasional mid-week bump
                series.append({"day": d, "count": base + jitter + bump})
            self.defect_trends[defect] = series  # type: ignore
        
        self.defects = [
            {"type": t, "count": r.randint(4, 45), "fill": PALETTE[i % len(PALETTE)]}
            for i, t in enumerate(DEFECT_TYPES)
        ]

        # AI Trends donut
        self.ai_trends = {"AI Correct": 72, "False Positive": 18, "False Negative": 10}

        # Performance (Hourly)
        hours = ["4h", "8h", "12h", "16h", "20h", "24h"]
        self.performance_hourly = [
            {"t": t, "Uptime": round(r.uniform(60, 98), 2), "Defect Rate": round(r.uniform(3, 20), 2)}
            for t in hours
        ]
        # Performance (Daily)
        dlabels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        self.performance_daily = [
            {"t": t, "Uptime": round(r.uniform(65, 95), 2), "Defect Rate": round(r.uniform(4, 16), 2)}
            for t in dlabels
        ]

        # Uptime 7d bars
        self.uptime_7d = [{"day": d, "uptime": round(r.uniform(20, 60), 2)} for d in days]
        self.uptime_7d[3]["uptime"] = round(r.uniform(55, 75), 2)  # Wed spike


        # Site Trends (Lakewood, Ramos, Clanton)
        def _series(base: float, jitter: float) -> List[float]:
            return [max(0.0, min(100.0, r.uniform(base - jitter, base + jitter))) for _ in range(7)]

        days_dates = ["Jul 1", "Jul 2", "Jul 3", "Jul 4", "Jul 5", "Jul 6", "Jul 7"]

        # Baselines chosen to reflect your index.py flavor
        yield_series = {
            "Lakewood": _series(95, 6),
            "Ramos": _series(90, 8),
            "Clanton": _series(70, 10),
        }
        defect_series = {
            "Lakewood": _series(3.5, 1.2),
            "Ramos": _series(3.0, 1.2),
            "Clanton": _series(9.0, 1.5),
        }
        uptime_series = {
            "Lakewood": _series(94, 4),
            "Ramos": _series(92, 5),
            "Clanton": _series(87, 5),
        }

        def _format(metric_map):
            out = []
            for i, d in enumerate(days_dates):
                row = {"d": d}
                for s in self.sites:
                    row[s] = metric_map[s][i]
                out.append(row)
            return out

        self.site_trends = {
            "Yield": _format(yield_series),
            "Defect Rate": _format(defect_series),
            "Uptime": _format(uptime_series),
        }

    # ── Derived vars for clean bindings ─────────────────────
    @rx.var
    def current_defect_series(self) -> List[Dict[str, Union[str, int]]]:
        return self.defect_trends.get(self.defect_filter, [])

    @rx.var
    def performance_series(self) -> List[Dict[str, Union[str, float]]]:
        return self.performance_hourly if self.perf_granularity == "Hourly" else self.performance_daily

    @rx.var
    def current_site_series(self) -> List[Dict[str, Union[str, float]]]:
        return self.site_trends.get(self.site_metric, [])
    
    @rx.var
    def defects_legend(self) -> List[Dict[str, Union[str, int, float]]]:
        total = sum(int(d["count"]) for d in self.defects) or 1
        out: List[Dict[str, Union[str, int, float]]] = []
        for d in self.defects:
            c = int(d["count"])
            pct = round((c / total) * 100.0, 1)
            out.append({
                "type": str(d["type"]),
                "count": c,
                "pct": pct,
                "fill": str(d.get("fill", "#94a3b8")),
            })
        # sort by count desc so biggest are first
        out.sort(key=lambda x: int(x["count"]), reverse=True)
        return out

    # ── Lifecycle ───────────────────────────────────────────
    def on_mount(self):
        self._seed()
        # one nudge so the UI shows motion right after mount
        self.refresh_tick()

    def refresh_tick(self):
        if not self.auto_refresh:
            return

        r = random.Random()

        # Defect counts (current filter)
        arr = self.defect_trends.get(self.defect_filter, [])
        for v in arr:
            v["count"] = max(0, int(v["count"]) + r.randint(-2, 2))

        # AI donut (normalize to 100)
        c = max(0, self.ai_trends["AI Correct"] + r.randint(-2, 2))
        fp = max(0, self.ai_trends["False Positive"] + r.randint(-2, 2))
        fn = max(0, self.ai_trends["False Negative"] + r.randint(-2, 2))
        total = c + fp + fn or 1
        c = int(round(c / total * 100))
        fp = int(round(fp / total * 100))
        fn = max(0, 100 - c - fp)
        self.ai_trends = {"AI Correct": c, "False Positive": fp, "False Negative": fn}

        # Performance lines
        for p in self.performance_series:
            p["Uptime"] = round(max(0, min(100, float(p["Uptime"]) + r.uniform(-2.5, 2.5))), 2)
            p["Defect Rate"] = round(max(0, min(100, float(p["Defect Rate"]) + r.uniform(-1.0, 1.0))), 2)

        # Uptime bars
        for b in self.uptime_7d:
            b["uptime"] = round(max(0, min(100, float(b["uptime"]) + r.uniform(-3.0, 3.0))), 2)

        # Site trends – nudge current metric
        for row in self.current_site_series:
            for s in self.sites:
                row[s] = round(max(0, min(100, float(row[s]) + r.uniform(-2.0, 2.0))), 2)

        for i, d in enumerate(self.defects):
            d["count"] = round(max(0, int(d["count"]) + r.randint(-2, 2)), 2)
            # keep colors stable
            d["fill"] = d.get("fill", PALETTE[i % len(PALETTE)])

    # ── Event handlers ──────────────────────────────────────
    @rx.event
    def set_overview_filter(self, v: str):
        self.overview_filter = v

    @rx.event
    def set_defect_filter(self, v: DefectKind):
        self.defect_filter = v

    @rx.event
    def set_perf_hourly(self):
        self.perf_granularity = "Hourly"

    @rx.event
    def set_perf_daily(self):
        self.perf_granularity = "Daily"

    @rx.event
    def set_metric_yield(self):
        self.site_metric = "Yield"

    @rx.event
    def set_metric_defects(self):
        self.site_metric = "Defect Rate"

    @rx.event
    def set_metric_uptime(self):
        self.site_metric = "Uptime"

    @rx.event
    def toggle_refresh(self):
        self.auto_refresh = not self.auto_refresh
    
    @rx.var
    def has_messages(self) -> bool:
        return len(self.messages) > 0

    @rx.event
    def quick_ask(self, text: str):
        """Set input to a suggested prompt and send it."""
        self.input_text = text
        self.send_message()



# ────────────────────────── Small UI helpers ──────────────────────────
def _card(title_icon: str, title: str, *children) -> rx.Component:
    return rx.box(
        rx.box(
            rx.hstack(rx.icon(title_icon), rx.text(f" {title}", as_="span"), align="center"),
            class_name="ai-card-title ai-card-pad",
        ),
        rx.box(*children, class_name="ai-card-pad"),
        class_name="ai-card",
    )


# ────────────────────────── Sections ──────────────────────────
def _header() -> rx.Component:
    return rx.box(
        rx.box(
            rx.text("Line Insights", class_name="ai-title"),
            rx.text("Strategic analysis and trends from inspection data", class_name="ai-sub"),
        ),
        rx.hstack(
            rx.button(
                rx.icon("rotate-cw"),
                rx.text(" Refresh Now", as_="span"),
                class_name="ai-button",
                on_click=InspectraLineInsightsState.refresh_tick,
            ),
            rx.button(
                rx.icon("download"),
                rx.text(" Export", as_="span"),
                class_name="ai-button",
                on_click=lambda: rx.console_log("Export clicked"),
            ),
            rx.box(
                rx.text("Auto Refresh", as_="span", class_name="ai-muted", margin_right="6px"),
                rx.box(class_name=rx.cond(InspectraLineInsightsState.auto_refresh, "ai-dot", "ai-dot off")),
                class_name="ai-chip toggle",
                on_click=InspectraLineInsightsState.toggle_refresh,
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
        rx.hstack(
            rx.text("Review all insights and analytics", class_name="ai-muted"),
            rx.spacer(),
            rx.select(
                ["All", "Week", "Month", "Quarter"],
                value=InspectraLineInsightsState.overview_filter,
                on_change=InspectraLineInsightsState.set_overview_filter,
                class_name="ai-select",
            ),
        ),
        class_name="ai-row",
    )


def _defect_trends() -> rx.Component:
    selector = rx.select(
        DEFECT_TYPES,
        value=InspectraLineInsightsState.defect_filter,
        on_change=InspectraLineInsightsState.set_defect_filter,
        class_name="ai-select",
    )

    header = rx.box(
        rx.hstack(
            rx.hstack(rx.icon("bar-chart-2"), rx.text(" Defect Trends", as_="span"), align="center"),
            rx.spacer(),
            selector,
            align="center",
            width="100%",
        ),
        class_name="ai-card-title ai-card-pad",
    )

    bars = rx.recharts.bar_chart(
        rx.recharts.cartesian_grid(stroke_dasharray="3 3"),
        rx.recharts.x_axis(data_key="day"),
        rx.recharts.y_axis(),
        rx.recharts.tooltip(),
        rx.recharts.bar(data_key="count", radius=[4, 4, 0, 0], fill=PALETTE[0]),
        data=InspectraLineInsightsState.current_defect_series,  # type: ignore
        width="100%",
        height=260,
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

    # Feed (only shown when there are messages)
    feed = rx.box(
        rx.foreach(InspectraLineInsightsState.messages, lambda m: bubble(m)),
        class_name="ai-chat-feed",
    )

    # Empty placeholder (shown when there are no messages)
    empty = rx.box(
        rx.icon("bot", size=28, color="#111827"),
        rx.html("<h4>How can I help?</h4>"),
        rx.html("<p>Try a prompt below to explore trends.</p>"),
        rx.box(
            rx.button("Top 3 rising defects", class_name="ai-chip-btn",
                      on_click=lambda: InspectraLineInsightsState.quick_ask("What are the top 3 rising defects this week?")),
            rx.button("Volatility: Weld Cracks", class_name="ai-chip-btn",
                      on_click=lambda: InspectraLineInsightsState.quick_ask("Show volatility over 7 days for Weld Cracks")),
            rx.button("Compare sites", class_name="ai-chip-btn",
                      on_click=lambda: InspectraLineInsightsState.quick_ask("Compare defect rate trends for Lakewood vs Ramos")),
            rx.button("Peak times today", class_name="ai-chip-btn",
                      on_click=lambda: InspectraLineInsightsState.quick_ask("When were peak defect times today?")),
            class_name="ai-samples",
        ),
        class_name="ai-chat-empty",
    )

    # Input pinned at bottom
    input_row = rx.box(
        rx.input(
            placeholder='Ask about trends (e.g., "Show volatility for Weld Cracks").',
            value=InspectraLineInsightsState.input_text,
            on_change=InspectraLineInsightsState.set_input,
            class_name="ai-select",
            style={"flex": "1"},
        ),
        rx.button(
            rx.icon("send"), rx.text(" Send", as_="span"),
            class_name="ai-button",
            on_click=InspectraLineInsightsState.send_message,
        ),
        class_name="ai-chat-input",
    )

    # Body: fixed height; show feed OR empty screen; input fixed at bottom
    body = rx.box(
        rx.cond(InspectraLineInsightsState.has_messages, feed, empty),
        input_row,
        class_name="ai-chat",
    )

    return _card("message-square", "Ask Inspectra", body)

def _perf_tabs() -> rx.Component:
    return rx.box(
        rx.button(
            "Hourly",
            class_name=rx.cond(InspectraLineInsightsState.perf_granularity == "Hourly", "ai-tab active", "ai-tab"),
            on_click=InspectraLineInsightsState.set_perf_hourly,
        ),
        rx.button(
            "Daily",
            class_name=rx.cond(InspectraLineInsightsState.perf_granularity == "Daily", "ai-tab active", "ai-tab"),
            on_click=InspectraLineInsightsState.set_perf_daily,
        ),
        class_name="ai-tabs",
    )

def _defect_breakdown() -> rx.Component:
    # Donut chart
    pie = rx.recharts.pie_chart(
        rx.recharts.tooltip(),
        rx.recharts.pie(
            data=InspectraLineInsightsState.defects,
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

    # Custom, scrollable legend (2 columns)
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

    return _card("pie-chart", "Defect Breakdown", body)

def _performance_trends() -> rx.Component:
    chart = rx.recharts.line_chart(
        rx.recharts.cartesian_grid(stroke_dasharray="3 3"),
        rx.recharts.x_axis(data_key="t"),
        rx.recharts.y_axis(domain=[0, 100]),
        rx.recharts.tooltip(),
        rx.recharts.legend(),
        rx.recharts.line(type_="monotone", data_key="Uptime", stroke=PALETTE[0], dot={"r": 3, "fill": "#fff", "stroke": PALETTE[0]}),
        rx.recharts.line(type_="monotone", data_key="Defect Rate", stroke=PALETTE[2], dot={"r": 3, "fill": "#fff", "stroke": PALETTE[2]}),
        data=InspectraLineInsightsState.performance_series,  # type: ignore
        width="100%",
        height=260,
    )

    return _card("activity", "Performance Trends", _perf_tabs(), chart)

def _uptime_7d() -> rx.Component:
    chart = rx.recharts.bar_chart(
        rx.recharts.cartesian_grid(stroke_dasharray="3 3"),
        rx.recharts.x_axis(data_key="day"),
        rx.recharts.y_axis(domain=[0, 80]),
        rx.recharts.tooltip(),
        rx.recharts.bar(data_key="uptime", radius=[4, 4, 0, 0], fill=PALETTE[0]),
        data=InspectraLineInsightsState.uptime_7d, width="100%", height=260,
    )
    return _card("calendar", "7 Days Uptime Trends", chart)

def _site_tabs() -> rx.Component:
    return rx.box(
        rx.button(
            "Yield",
            class_name=rx.cond(InspectraLineInsightsState.site_metric == "Yield", "ai-tab active", "ai-tab"),
            on_click=InspectraLineInsightsState.set_metric_yield,
        ),
        rx.button(
            "Defect Rate",
            class_name=rx.cond(InspectraLineInsightsState.site_metric == "Defect Rate", "ai-tab active", "ai-tab"),
            on_click=InspectraLineInsightsState.set_metric_defects,
        ),
        rx.button(
            "Uptime",
            class_name=rx.cond(InspectraLineInsightsState.site_metric == "Uptime", "ai-tab active", "ai-tab"),
            on_click=InspectraLineInsightsState.set_metric_uptime,
        ),
        class_name="ai-tabs",
    )

def _site_trends() -> rx.Component:
    legend = rx.hstack(
        rx.box(style={"background": PALETTE[0]}, class_name="ai-legend-dot"), rx.text("Lakewood", class_name="ai-muted"),
        rx.box(style={"background": PALETTE[1], "margin-left":"14px"}, class_name="ai-legend-dot"), rx.text("Ramos", class_name="ai-muted"),
        rx.box(style={"background": PALETTE[7], "margin-left":"14px"}, class_name="ai-legend-dot"), rx.text("Clanton", class_name="ai-muted"),
        align="center",
        wrap="wrap",
        gap="6px",
    )

    chart = rx.recharts.line_chart(
        rx.recharts.cartesian_grid(stroke_dasharray="3 3"),
        rx.recharts.x_axis(data_key="d"),
        rx.recharts.y_axis(domain=[0, 100]),
        rx.recharts.tooltip(),
        rx.recharts.legend(),
        rx.recharts.line(type_="monotone", data_key="Lakewood", stroke=PALETTE[0], dot={"r": 2, "fill": "#fff", "stroke": PALETTE[0]}),
        rx.recharts.line(type_="monotone", data_key="Ramos", stroke=PALETTE[1], dot={"r": 2, "fill": "#fff", "stroke": PALETTE[1]}),
        rx.recharts.line(type_="monotone", data_key="Clanton", stroke=PALETTE[7], dot={"r": 2, "fill": "#fff", "stroke": PALETTE[7]}),
        data=InspectraLineInsightsState.current_site_series,  # type: ignore
        width="100%", height=320, margin={"top": 6, "right": 12, "left": 0, "bottom": 4},
    )

    return rx.box(
        rx.box(
            rx.hstack(rx.icon("building-2"), rx.text(" Manufacturing Site Trends", as_="span", weight="bold"), align="center"),
            class_name="ai-card-title ai-card-pad",
        ),
        rx.box(rx.hstack(_site_tabs(), rx.spacer(), legend), class_name="ai-card-pad"),
        rx.box(chart, class_name="ai-card-pad"),
        class_name="ai-card",
    )

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
                _uptime_7d(),
                class_name="ai-grid two",
            ),

            # NEW: full defect breakdown (donut + long legend)
            _defect_breakdown(),

            # _site_trends(),
            class_name="ai-page",
        ),
        on_mount=InspectraLineInsightsState.on_mount,
        class_name="ai-shell",
    )

