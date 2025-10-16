import reflex as rx
from typing import List, Dict, Literal, Optional

# ────────────────────────── Types / Data ──────────────────────────
Severity = Literal["Critical", "High", "Medium", "Low"]
Status = Literal["Unacknowledged", "Acknowledged", "Escalated"]
Alert = Dict[str, str]

MOCK_ALERTS: List[Alert] = [
    # Memphis (A lines)
    {"timestamp_day": "15 JAN", "timestamp_time": "02:00 PM", "line": "Line A-1", "plant": "Memphis Plant",
     "description": "Defect rate exceeds threshold (8.5%)", "severity": "Critical", "status": "Unacknowledged", "tone": "red"},
    {"timestamp_day": "15 JAN", "timestamp_time": "01:45 PM", "line": "Line A-2", "plant": "Memphis Plant",
     "description": "Model version mismatch detected", "severity": "Medium", "status": "Acknowledged", "tone": "blue"},
    {"timestamp_day": "15 JAN", "timestamp_time": "12:40 PM", "line": "Line A-1", "plant": "Memphis Plant",
     "description": "Edge server CPU spiking", "severity": "High", "status": "Acknowledged", "tone": "amber"},
    {"timestamp_day": "15 JAN", "timestamp_time": "11:20 AM", "line": "Line A-2", "plant": "Memphis Plant",
     "description": "Camera 3 dropped frames intermittently", "severity": "Low", "status": "Acknowledged", "tone": "gray"},
    # Austin (B/C)
    {"timestamp_day": "15 JAN", "timestamp_time": "02:00 PM", "line": "Line B-2", "plant": "Austin Plant",
     "description": "Camera calibration required - below 85%", "severity": "High", "status": "Acknowledged", "tone": "amber"},
    {"timestamp_day": "15 JAN", "timestamp_time": "01:50 PM", "line": "Line B-1", "plant": "Austin Plant",
     "description": "Temperature sensor anomaly", "severity": "High", "status": "Acknowledged", "tone": "amber"},
    {"timestamp_day": "15 JAN", "timestamp_time": "01:35 PM", "line": "Line C-1", "plant": "Austin Plant",
     "description": "Production line - maintenance required", "severity": "Critical", "status": "Escalated", "tone": "red"},
    {"timestamp_day": "15 JAN", "timestamp_time": "12:10 PM", "line": "Line B-2", "plant": "Austin Plant",
     "description": "Conveyor speed variance detected", "severity": "Medium", "status": "Unacknowledged", "tone": "blue"},
    # Detroit (D)
    {"timestamp_day": "15 JAN", "timestamp_time": "02:00 PM", "line": "Line D-1", "plant": "Detroit Plant",
     "description": "Inspection rate below optimal", "severity": "Low", "status": "Acknowledged", "tone": "gray"},
    {"timestamp_day": "15 JAN", "timestamp_time": "01:10 PM", "line": "Line D-1", "plant": "Detroit Plant",
     "description": "Network latency to storage", "severity": "Medium", "status": "Unacknowledged", "tone": "blue"},
    {"timestamp_day": "15 JAN", "timestamp_time": "12:50 PM", "line": "Line D-1", "plant": "Detroit Plant",
     "description": "GPU memory nearing threshold", "severity": "High", "status": "Acknowledged", "tone": "amber"},
    # Extra rows for pagination
    {"timestamp_day": "15 JAN", "timestamp_time": "12:35 PM", "line": "Line C-1", "plant": "Austin Plant",
     "description": "Model drift suspected on station 2", "severity": "High", "status": "Unacknowledged", "tone": "amber"},
    {"timestamp_day": "15 JAN", "timestamp_time": "12:20 PM", "line": "Line B-1", "plant": "Austin Plant",
     "description": "PLC heartbeat missed (2s)", "severity": "Low", "status": "Acknowledged", "tone": "gray"},
    {"timestamp_day": "15 JAN", "timestamp_time": "11:55 AM", "line": "Line A-1", "plant": "Memphis Plant",
     "description": "Part ejection timing offset", "severity": "Medium", "status": "Acknowledged", "tone": "blue"},
    {"timestamp_day": "15 JAN", "timestamp_time": "11:35 AM", "line": "Line A-2", "plant": "Memphis Plant",
     "description": "Station 4 lighting flicker", "severity": "Low", "status": "Acknowledged", "tone": "gray"},
    {"timestamp_day": "15 JAN", "timestamp_time": "11:10 AM", "line": "Line B-2", "plant": "Austin Plant",
     "description": "Unexpected stop: E-Stop pressed", "severity": "Critical", "status": "Escalated", "tone": "red"},
    {"timestamp_day": "15 JAN", "timestamp_time": "10:55 AM", "line": "Line D-1", "plant": "Detroit Plant",
     "description": "Low disk space on node d-01", "severity": "Medium", "status": "Acknowledged", "tone": "blue"},
    {"timestamp_day": "15 JAN", "timestamp_time": "10:40 AM", "line": "Line B-1", "plant": "Austin Plant",
     "description": "AI service restart completed", "severity": "Low", "status": "Acknowledged", "tone": "gray"},
    {"timestamp_day": "15 JAN", "timestamp_time": "10:20 AM", "line": "Line C-1", "plant": "Austin Plant",
     "description": "Sensor calibration due in 2 days", "severity": "Low", "status": "Acknowledged", "tone": "gray"},
    {"timestamp_day": "15 JAN", "timestamp_time": "10:05 AM", "line": "Line A-1", "plant": "Memphis Plant",
     "description": "Sudden drop in yield (-3%)", "severity": "High", "status": "Unacknowledged", "tone": "amber"},
    {"timestamp_day": "15 JAN", "timestamp_time": "09:55 AM", "line": "Line B-2", "plant": "Austin Plant",
     "description": "Thermal envelope exceeded briefly", "severity": "Medium", "status": "Acknowledged", "tone": "blue"},
    {"timestamp_day": "15 JAN", "timestamp_time": "09:40 AM", "line": "Line D-1", "plant": "Detroit Plant",
     "description": "Operator login failure attempts", "severity": "Low", "status": "Acknowledged", "tone": "gray"},
    {"timestamp_day": "15 JAN", "timestamp_time": "09:25 AM", "line": "Line A-1", "plant": "Memphis Plant",
     "description": "Model reload completed", "severity": "Low", "status": "Acknowledged", "tone": "gray"},
    {"timestamp_day": "15 JAN", "timestamp_time": "09:10 AM", "line": "Line C-1", "plant": "Austin Plant",
     "description": "Throughput improvement (+4%)", "severity": "Low", "status": "Acknowledged", "tone": "gray"},
]

# ────────────────────────── STATE (in-memory + modal) ──────────────────────────
class AlertsState(rx.State):
    # Filters
    severity: str = "All"
    status: str = "All"
    plant: str = "All Plants"
    line: str = "All Lines"
    timeframe: str = "Last 24h"

    # Pagination
    offset: int = 0
    limit: int = 10

    # Data
    alerts: List[Alert] = MOCK_ALERTS

    # Modal state (copy fields to avoid dict indexing with Vars)
    modal_open: bool = False
    sel_idx: Optional[int] = None  # index into alerts for mutation
    sel_title_line: str = ""
    sel_title_desc: str = ""
    sel_severity: str = ""     # Critical/High/Medium/Low
    sel_status: str = ""       # Unacknowledged/Acknowledged/Escalated
    sel_plant: str = ""
    sel_line: str = ""

    # Demo metrics/timeline for modal
    sel_defect_rate: str = "8.5%"
    sel_uptime: str = "92.3%"
    sel_threshold: str = "5%"
    sel_confidence: str = "94.2%"
    timeline: List[Dict[str, str]] = [
        {"label": "Alert triggered", "ago": "15m ago", "tone": "red"},
        {"label": "Operator Confirmation", "ago": "45m ago", "tone": "green"},
        {"label": "Defect Logged", "ago": "2h ago", "tone": "green"},
    ]

    # Options from data
    @rx.var
    def plant_options(self) -> List[str]:
        return ["All Plants"] + sorted({a["plant"] for a in self.alerts})

    @rx.var
    def line_options(self) -> List[str]:
        return ["All Lines"] + sorted({a["line"] for a in self.alerts})

    # Filtering
    def _time_ok(self, _a: Alert) -> bool:
        return True

    @rx.var
    def filtered_alerts(self) -> List[Alert]:
        data = self.alerts
        if self.severity != "All":
            data = [a for a in data if a["severity"] == self.severity]
        if self.status != "All":
            data = [a for a in data if a["status"] == self.status]
        if self.plant != "All Plants":
            data = [a for a in data if a["plant"] == self.plant]
        if self.line != "All Lines":
            data = [a for a in data if a["line"] == self.line]
        data = [a for a in data if self._time_ok(a)]
        return list(data)

    # Pagination deriveds
    @rx.var
    def total_items(self) -> int:
        return len(self.filtered_alerts)

    @rx.var
    def page_number(self) -> int:
        return (self.offset // self.limit) + 1

    @rx.var
    def total_pages(self) -> int:
        n = self.total_items
        return (n // self.limit) + (1 if n % self.limit else 0) or 1

    @rx.var
    def page_label(self) -> str:
        return f"Page {min(self.page_number, self.total_pages)} of {self.total_pages}"

    @rx.var
    def can_prev(self) -> bool:
        return self.offset > 0

    @rx.var
    def can_next(self) -> bool:
        return self.offset + self.limit < self.total_items

    @rx.var
    def current_page_alerts(self) -> List[Alert]:
        start, end = self.offset, self.offset + self.limit
        return self.filtered_alerts[start:end]

    # Filter events
    @rx.event
    def set_severity(self, v: str): self._set_filter("severity", v or "All")
    @rx.event
    def set_status(self, v: str): self._set_filter("status", v or "All")
    @rx.event
    def set_plant(self, v: str): self._set_filter("plant", v or "All Plants")
    @rx.event
    def set_line(self, v: str): self._set_filter("line", v or "All Lines")
    @rx.event
    def set_timeframe(self, v: str): self._set_filter("timeframe", v or "Last 24h")

    def _set_filter(self, key: str, value: str):
        setattr(self, key, value)
        self.offset = 0

    @rx.event
    def clear_filters(self):
        self.severity, self.status = "All", "All"
        self.plant, self.line = "All Plants", "All Lines"
        self.timeframe = "Last 24h"
        self.offset = 0

    # Pagination events
    @rx.event
    def prev_page(self):
        self.offset = max(self.offset - self.limit, 0)

    @rx.event
    def next_page(self):
        if self.offset + self.limit < self.total_items:
            self.offset += self.limit

    # ── Modal events
    @rx.event
    def open_details(self, alert: dict):
        """Open modal for this alert and copy fields into dedicated state vars."""
        # Find an index in the full alerts list (first match by 3-tuple)
        idx = next(
            (i for i, a in enumerate(self.alerts)
             if a["plant"] == alert["plant"]
             and a["line"] == alert["line"]
             and a["description"] == alert["description"]),
            None,
        )
        self.sel_idx = idx
        self.sel_title_line = alert["line"]
        self.sel_title_desc = alert["description"]
        self.sel_severity = alert["severity"]
        self.sel_status = alert["status"]
        self.sel_plant = alert["plant"]
        self.sel_line = alert["line"]
        # Demo metrics (you can compute these per alert if you have data)
        self.sel_defect_rate = "8.5%" if "Defect rate" in alert["description"] else "5.2%"
        self.sel_uptime = "92.3%"
        self.sel_threshold = "5%"
        self.sel_confidence = "94.2%"
        self.modal_open = True

    @rx.event
    def close_details(self):
        self.modal_open = False

    @rx.event
    def acknowledge(self):
        """Set status to Acknowledged in modal + table."""
        self.sel_status = "Acknowledged"
        # Update the corresponding row in base data
        if self.sel_idx is not None and 0 <= self.sel_idx < len(self.alerts):
            self.alerts[self.sel_idx]["status"] = "Acknowledged"

    @rx.event
    def escalate(self):
        """Set status to Escalated in modal + table."""
        self.sel_status = "Escalated"
        if self.sel_idx is not None and 0 <= self.sel_idx < len(self.alerts):
            self.alerts[self.sel_idx]["status"] = "Escalated"
    
    @rx.var
    def sel_title(self) -> str:
        if not self.sel_title_line and not self.sel_title_desc:
            return ""
        return f"{self.sel_title_line} - {self.sel_title_desc}"
    
    # ── escalate sub-modal state
    escalate_open: bool = False
    escalate_to: str = ""
    escalate_options: List[str] = [
        "QA Manager",
        "Plant Manager",
        "Operations Head",
        "Maintenance Team",
    ]
    
    # ---------- Sorting: Critical/High first, Acknowledged last ----------
    @rx.var
    def filtered_alerts(self) -> List[Alert]:
        data = self.alerts
        if self.severity != "All":
            data = [a for a in data if a["severity"] == self.severity]
        if self.status != "All":
            data = [a for a in data if a["status"] == self.status]
        if self.plant != "All Plants":
            data = [a for a in data if a["plant"] == self.plant]
        if self.line != "All Lines":
            data = [a for a in data if a["line"] == self.line]
        data = [a for a in data if self._time_ok(a)]

        # Priority: status then severity
        status_pri = {"Unacknowledged": 0, "Escalated": 1, "Acknowledged": 2}
        sev_pri = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        data = sorted(
            data,
            key=lambda a: (
                status_pri.get(a["status"], 9),
                sev_pri.get(a["severity"], 9),
            ),
        )
        return data

    # ---------- Acknowledge should close the main modal ----------
    @rx.event
    def acknowledge(self):
        """Set status to Acknowledged, update table, and close modal."""
        self.sel_status = "Acknowledged"
        if self.sel_idx is not None and 0 <= self.sel_idx < len(self.alerts):
            self.alerts[self.sel_idx]["status"] = "Acknowledged"
        self.modal_open = False  # close the main modal

    # ---------- Escalate sub-modal handlers ----------
    @rx.event
    def open_escalate(self):
        self.escalate_open = True
        self.escalate_to = ""

    @rx.event
    def close_escalate(self):
        self.escalate_open = False

    @rx.event
    def set_escalate_to(self, value: str):
        self.escalate_to = value

    @rx.event
    def confirm_escalate(self):
        # If nothing chosen, you could early return or default; we proceed.
        self.sel_status = "Escalated"
        if self.sel_idx is not None and 0 <= self.sel_idx < len(self.alerts):
            self.alerts[self.sel_idx]["status"] = "Escalated"
        self.escalate_open = False  # close small popup
        # keep the main modal open after escalation (per your mock)
    
    @rx.var
    def sel_title(self) -> str:
        if not self.sel_title_line and not self.sel_title_desc:
            return ""
        return f"{self.sel_title_line} - {self.sel_title_desc}"

    @rx.var
    def escalate_alert_summary(self) -> str:
        return f"Alert: {self.sel_title_desc}" if self.sel_title_desc else ""

    @rx.var
    def escalate_line_summary(self) -> str:
        return f"Line:  {self.sel_title_line}" if self.sel_title_line else ""
        


# ────────────────────────── UI Helpers ──────────────────────────
def _pill(text: str, tone: str) -> rx.Component:
    tone_map = {
        "red": ("#FEE2E2", "#991B1B"),
        "amber": ("#FEF3C7", "#92400E"),
        "blue": ("#DBEAFE", "#1E3A8A"),
        "gray": ("#E5E7EB", "#374151"),
        "green": ("#DCFCE7", "#166534"),
    }
    bg, fg = tone_map.get(tone, ("#E5E7EB", "#374151"))
    return rx.box(
        rx.text(text, size="2", weight="medium"),
        padding="4px 8px",
        border_radius="9999px",
        background_color=bg,
        color=fg,
        display="inline-flex",
        align_items="center",
        gap="6px",
    )

def _severity_badge(level) -> rx.Component:
    return rx.cond(
        level == "Critical", _pill(level, "red"),
        rx.cond(level == "High", _pill(level, "amber"),
        rx.cond(level == "Medium", _pill(level, "blue"), _pill(level, "gray"))),
    )

def _status_badge(status) -> rx.Component:
    return rx.cond(
        status == "Unacknowledged", _pill(status, "red"),
        rx.cond(status == "Escalated", _pill(status, "amber"),
        rx.cond(status == "Acknowledged", _pill(status, "blue"), _pill(status, "gray"))),
    )

def _timestamp(day: str, time: str) -> rx.Component:
    return rx.vstack(
        rx.text(day, weight="bold", color="#111827"),
        rx.text(time, size="2", color="#6B7280"),
        align_items="start",
        gap="2px",
    )

def _line_cell(line: str, plant: str) -> rx.Component:
    return rx.vstack(
        rx.text(line, weight="medium"),
        rx.text(plant, size="2", color="#6B7280"),
        align_items="start",
        gap="2px",
    )

def _filter_select(label: str, value, items, on_change) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="2", color="#4B5563"),
        rx.select(
            items,
            value=value,
            on_change=on_change,
            width="100%",
            radius="medium",
            variant="surface",
        ),
        gap="6px",
        width="100%",
    )

# Table column styles (fixed layout)
COL_STYLES = [
    {"min_width": "140px", "width": "160px"},
    {"min_width": "160px", "width": "200px"},
    {"min_width": "360px", "width": "100%"},
    {"min_width": "140px", "width": "160px"},
    {"min_width": "180px", "width": "220px"},
    {"min_width": "100px", "width": "120px", "text_align": "right"},
]

def _col_style(i: int) -> Dict[str, str]:
    return COL_STYLES[i] if i < len(COL_STYLES) else {}

# ────────────────────────── Table Rows ──────────────────────────
def _alert_row(alert: Alert) -> rx.Component:
    color_map = {"red": "#F87171", "amber": "#FBBF24", "blue": "#93C5FD", "gray": "#D1D5DB"}
    accent = color_map.get(alert.get("tone", "gray"), "#D1D5DB")

    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.box(width="4px", height="30px", border_radius="6px", background_color=accent),
                _timestamp(alert["timestamp_day"], alert["timestamp_time"]),
                align="center",
                gap="10px",
            ),
            style=_col_style(0),
        ),
        rx.table.cell(_line_cell(alert["line"], alert["plant"]), style=_col_style(1)),
        rx.table.cell(rx.text(alert["description"]), style=_col_style(2)),
        rx.table.cell(_severity_badge(alert["severity"]), style=_col_style(3)),
        rx.table.cell(_status_badge(alert["status"]), style=_col_style(4)),
        rx.table.cell(
            rx.hstack(
                rx.icon("arrow-up"),
                rx.icon(
                    "eye",
                    on_click=lambda a=alert: AlertsState.open_details(a),  # open modal with this alert
                    cursor="pointer",
                ),
                justify="end",
                align="center",
                gap="12px",
            ),
            style=_col_style(5),
        ),
    )

# ────────────────────────── Modal (detail view) ──────────────────────────
def _metric_card(label: str, value: str) -> rx.Component:
    return rx.box(
        rx.text(label, size="2", color="#6B7280"),
        rx.text(value, weight="medium"),
        border="1px solid #E5E7EB",
        border_radius="12px",
        padding="16px",
        background_color="#FDFDFD",
    )

def _timeline_item(label: str, ago: str, tone: str) -> rx.Component:
    color_map = {"red": "#F87171", "green": "#34D399", "amber": "#FBBF24", "gray": "#D1D5DB"}
    bar = color_map.get(tone, "#D1D5DB")
    return rx.hstack(
        rx.box(width="3px", height="26px", border_radius="6px", background_color=bar),
        rx.text(label),
        rx.spacer(),
        rx.text(ago, color="#6B7280"),
        align="center",
        gap="10px",
        width="100%",
        padding_y="6px",
    )

def details_modal() -> rx.Component:
    # Render only when open (simple overlay + centered card)
    return rx.cond(
        AlertsState.modal_open,
        rx.box(
            # Dimmed backdrop
            rx.box(
                position="fixed",
                inset="0",
                background_color="rgba(15, 23, 42, 0.55)",
                z_index="49",
                on_click=AlertsState.close_details,
            ),
            # Modal card
            rx.box(
                # Header
                rx.hstack(
                    rx.hstack(
                        rx.text(AlertsState.sel_title, weight="bold"),
                        _severity_badge(AlertsState.sel_severity),
                        align="center",
                        gap="10px",
                    ),
                    rx.icon("x", cursor="pointer", on_click=AlertsState.close_details),
                    justify="between",
                    align="start",
                    margin_bottom="6px",
                ),
                rx.text("View detailed alert information, current metrics, and event timeline.", color="#6B7280"),

                # Alert Information
                rx.box(
                    rx.text("Alert Information", weight="medium", margin_top="18px", margin_bottom="8px"),
                    rx.grid(
                        rx.vstack(rx.text("Plant", size="2", color="#6B7280"), rx.text(AlertsState.sel_plant)),
                        rx.vstack(rx.text("Line", size="2", color="#6B7280"), rx.text(AlertsState.sel_line)),
                        rx.vstack(rx.text("Status", size="2", color="#6B7280"),
                                  _status_badge(AlertsState.sel_status)),
                        columns="1fr 1fr 1fr",
                        gap="16px",
                    ),
                ),

                # Current Metrics
                rx.box(
                    rx.text("Current Metrics", weight="medium", margin_top="18px", margin_bottom="8px"),
                    rx.grid(
                        _metric_card("Defect Rate", AlertsState.sel_defect_rate),
                        _metric_card("Uptime", AlertsState.sel_uptime),
                        _metric_card("Threshold", AlertsState.sel_threshold),
                        _metric_card("Confidence", AlertsState.sel_confidence),
                        columns="1fr 1fr",
                        gap="16px",
                    ),
                ),

                # Event Timeline
                rx.box(
                    rx.text("Event Timeline", weight="medium", margin_top="18px", margin_bottom="8px"),
                    rx.vstack(
                        rx.foreach(
                            AlertsState.timeline,
                            lambda ev: _timeline_item(ev["label"], ev["ago"], ev["tone"]),
                        ),
                        gap="6px",
                    ),
                ),

                # Footer actions
                rx.hstack(
                    rx.button(
                        rx.icon("check-circle"),
                        rx.text("Acknowledge"),
                        variant="soft",
                        color_scheme="green",
                        on_click=AlertsState.acknowledge,   # closes main modal now
                    ),
                    rx.button(
                        rx.icon("arrow-up"),
                        rx.text("Escalate"),
                        variant="soft",
                        color_scheme="red",
                        on_click=AlertsState.open_escalate,  # opens small popup
                    ),
                    justify="end",
                    padding_top="14px",
                ),
                position="fixed",
                left="50%",
                top="50%",
                transform="translate(-50%, -50%)",
                z_index="50",
                width="min(860px, 92vw)",
                background_color="#FFFFFF",
                border_radius="14px",
                padding="20px",
                box_shadow="0 20px 60px rgba(0,0,0,0.25)",
            ),
        ),
        None,
    )
    
def escalate_popup() -> rx.Component:
    return rx.cond(
        AlertsState.escalate_open,
        rx.box(
            # subtle overlay above the main modal
            rx.box(
                position="fixed",
                inset="0",
                background_color="rgba(15, 23, 42, 0.25)",
                z_index="59",
                on_click=AlertsState.close_escalate,
            ),
            # small centered card
            rx.box(
                # Header
                rx.hstack(
                    rx.text("Escalate Alert", weight="bold"),
                    rx.icon("x", cursor="pointer", on_click=AlertsState.close_escalate),
                    justify="between",
                    align="center",
                    margin_bottom="6px",
                ),
                rx.text(
                    "Escalate this alert to appropriate personnel with additional context.",
                    color="#6B7280",
                ),

                # Summary
                rx.box(
                    rx.text(AlertsState.escalate_alert_summary, weight="medium", margin_top="14px"),
                    rx.text(AlertsState.escalate_line_summary, color="#374151"),
                ),

                # Escalate to
                rx.box(
                    rx.text("Escalate To", weight="medium", margin_top="16px", margin_bottom="6px"),
                    rx.box(
                        rx.text("Select who to escalate to", size="2", color="#6B7280"),
                        border="1px solid #E5E7EB",
                        border_radius="10px",
                        padding="10px",
                        margin_bottom="8px",
                    ),
                    rx.radio(
                        AlertsState.escalate_options,
                        value=AlertsState.escalate_to,
                        on_change=AlertsState.set_escalate_to,
                        direction="column",
                    ),
                ),

                # Footer
                rx.hstack(
                    rx.spacer(),
                    rx.button("Cancel", variant="surface", on_click=AlertsState.close_escalate),
                    rx.button(
                        "Escalate",
                        variant="soft",
                        color_scheme="red",
                        on_click=AlertsState.confirm_escalate,
                        disabled=rx.cond(AlertsState.escalate_to != "", False, True),
                    ),
                    gap="10px",
                    margin_top="14px",
                ),

                position="fixed",
                left="50%",
                top="50%",
                transform="translate(-50%, -50%)",
                z_index="60",                           # above main modal (50)
                width="min(640px, 92vw)",
                background_color="#FFFFFF",
                border_radius="14px",
                padding="18px",
                box_shadow="0 16px 48px rgba(0,0,0,0.25)",
            ),
        ),
        None,
    )


# ────────────────────────── Sections ──────────────────────────
def filters_section() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.text("Filter alerts", weight="medium"),
            justify="between",
            width="100%",
            margin_bottom="10px",
        ),
        rx.grid(
            _filter_select("Severity",  AlertsState.severity,
                           ["All", "Critical", "High", "Medium", "Low"], AlertsState.set_severity),
            _filter_select("Status",    AlertsState.status,
                           ["All", "Unacknowledged", "Acknowledged", "Escalated"], AlertsState.set_status),
            _filter_select("Plant",     AlertsState.plant,
                           AlertsState.plant_options, AlertsState.set_plant),
            _filter_select("Line",      AlertsState.line,
                           AlertsState.line_options, AlertsState.set_line),
            _filter_select("Timeframe", AlertsState.timeframe,
                           ["Last 24h", "Last 7d", "Last 30d"], AlertsState.set_timeframe),
            columns="repeat(5, 1fr)",
            gap="16px",
            width="100%",
        ),
        background_color="#FFFFFF",
        padding="16px",
        border_radius="12px",
        box_shadow="0 1px 0 rgba(0,0,0,0.04)",
        width="100%",
    )

# Header + body table (aligned)
COL_STYLES = [
    {"min_width": "140px", "width": "160px"},
    {"min_width": "160px", "width": "200px"},
    {"min_width": "360px", "width": "100%"},
    {"min_width": "140px", "width": "160px"},
    {"min_width": "180px", "width": "220px"},
    {"min_width": "100px", "width": "120px", "text_align": "right"},
]
def _col_style(i: int) -> Dict[str, str]: return COL_STYLES[i]

def table_section() -> rx.Component:
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell("Timestamp",  style=_col_style(0)),
                rx.table.column_header_cell("Line / Cell", style=_col_style(1)),
                rx.table.column_header_cell("Description", style=_col_style(2)),
                rx.table.column_header_cell("Severity",    style=_col_style(3)),
                rx.table.column_header_cell("Status",      style=_col_style(4)),
                rx.table.column_header_cell("Actions",     style=_col_style(5)),
            )
        ),
        rx.table.body(rx.foreach(AlertsState.current_page_alerts, _alert_row)),
        width="100%",
        variant="surface",
        size="3",
        style={"table_layout": "fixed"},
    )

def pagination() -> rx.Component:
    return rx.hstack(
        rx.button(
            rx.icon("chevron-left"),
            variant="surface",
            on_click=AlertsState.prev_page,
            disabled=rx.cond(AlertsState.can_prev, False, True),
        ),
        rx.text(AlertsState.page_label),
        rx.button(
            rx.icon("chevron-right"),
            variant="surface",
            on_click=AlertsState.next_page,
            disabled=rx.cond(AlertsState.can_next, False, True),
        ),
        justify="end",
        align="center",
        gap="8px",
        width="100%",
        padding_top="8px",
    )

# ────────────────────────── Page ──────────────────────────
def index() -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.text("Alerts", size="6", weight="bold"),
            rx.text("Active alerts requiring attention", color="#6B7280"),
            rx.hstack(
                rx.button(rx.icon("calendar"), rx.text("Date range"), variant="soft"),
                rx.button("Clear all", variant="surface", on_click=AlertsState.clear_filters),
                justify="end",
                margin_top="12px",
            ),
            gap="6px",
        ),
        filters_section(),
        rx.box(
            table_section(),
            background_color="#FFFFFF",
            padding="8px",
            border_radius="12px",
            box_shadow="0 1px 0 rgba(0,0,0,0.04)",
            width="100%",
        ),
        pagination(),
        details_modal(),  # ← modal overlay renders on top when open
        escalate_popup(),
        gap="16px",
        width="100%",
        padding="48px",
        background_color="#F9FAFB",
        min_height="100vh",
    )
