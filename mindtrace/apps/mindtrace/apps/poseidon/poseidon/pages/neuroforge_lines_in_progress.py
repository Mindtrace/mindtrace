# poseidon/pages/neuroforge_lines_in_progress.py
import reflex as rx
from typing import List, Dict

# ---------- Brain options (for display/filter) ----------
BRAIN_OPTIONS = [
    {"key": "weld",           "name": "Weld Brain"},
    {"key": "laser_weld",     "name": "Laser Weld Brain"},
    {"key": "bead",           "name": "Bead Brain"},
    {"key": "paint",          "name": "Paint Brain"},
    {"key": "metal_forming",  "name": "Metal-Forming Brain"},
    {"key": "trim",           "name": "Trim Brain"},
    {"key": "gear_box",       "name": "Gear-Box Brain"},
    {"key": "stitching",      "name": "Stitching Brain"},
    {"key": "metal_stamping", "name": "Metal-Stamping Brain"},
]
BRAIN_NAMES = [b["name"] for b in BRAIN_OPTIONS]
BRAIN_KEY_TO_NAME = {b["key"]: b["name"] for b in BRAIN_OPTIONS}
BRAIN_NAME_TO_KEY = {b["name"]: b["key"] for b in BRAIN_OPTIONS}

# ---------- Dummy "in-progress" lines ----------
INPROGRESS_DUMMY: List[Dict] = [
    {"project_name": "Widget A Launch", "line_name": "Line-Alpha",  "location": "Plant 1 / Bay A",
     "brain": "weld", "stage": "Capturing", "progress": 32, "updated_at": "2025-09-29 11:04", "eta": "~15m"},
    {"project_name": "Widget A Launch", "line_name": "Line-Beta",   "location": "Plant 1 / Bay B",
     "brain": "laser_weld", "stage": "Labeling", "progress": 58, "updated_at": "2025-09-30 09:10", "eta": "Pending"},
    {"project_name": "Gizmo Refresh",   "line_name": "Line-Gamma",  "location": "Plant 2 / West",
     "brain": "bead", "stage": "Training", "progress": 74, "updated_at": "2025-09-30 12:22", "eta": "~25m"},
    {"project_name": "Gizmo Refresh",   "line_name": "Line-Delta",  "location": "Plant 2 / East",
     "brain": "paint", "stage": "Validating", "progress": 86, "updated_at": "2025-09-30 12:40", "eta": "~8m"},
    {"project_name": "Bolt Program",    "line_name": "Line-Epsilon","location": "Plant 3 / North",
     "brain": "metal_forming", "stage": "Queued", "progress": 0, "updated_at": "2025-09-30 10:02", "eta": "TBD"},
    {"project_name": "Bolt Program",    "line_name": "Line-Zeta",   "location": "Plant 3 / South",
     "brain": "trim", "stage": "Capturing", "progress": 19, "updated_at": "2025-09-30 11:51", "eta": "~30m"},
    {"project_name": "Widget B Ramp",   "line_name": "Line-Eta",    "location": "Plant 4 / Assembly",
     "brain": "gear_box", "stage": "Training", "progress": 41, "updated_at": "2025-09-30 12:01", "eta": "~50m"},
    {"project_name": "Widget B Ramp",   "line_name": "Line-Theta",  "location": "Plant 4 / Test",
     "brain": "stitching", "stage": "Validating", "progress": 92, "updated_at": "2025-09-30 12:48", "eta": "~3m"},
    {"project_name": "MegaMix Program", "line_name": "Line-Iota",   "location": "Plant 5 / North",
     "brain": "metal_stamping", "stage": "Labeling", "progress": 63, "updated_at": "2025-09-30 12:33", "eta": "Pending"},
    {"project_name": "MegaMix Program", "line_name": "Line-Kappa",  "location": "Plant 5 / South",
     "brain": "weld", "stage": "Queued", "progress": 0, "updated_at": "2025-09-30 10:45", "eta": "TBD"},
]

# ---------- State ----------
class LinesProgressState(rx.State):
    search_project: str = ""
    stage_filter: str = "All"
    brain_filter_key: str = "All"

    page: int = 1
    rows_per_page: int = 8

    # Cancel confirmation
    confirm_open: bool = False
    pending_cancel_line: str = ""
    cancelled_line_names: List[str] = []

    @rx.var
    def brain_name_options(self) -> list[str]:
        return ["All"] + BRAIN_NAMES

    @rx.var
    def stage_options(self) -> list[str]:
        stages = sorted(list({row["stage"] for row in INPROGRESS_DUMMY}))
        return ["All"] + stages

    def set_search_project(self, v: str):
        self.search_project = v
        self.page = 1

    def set_stage_filter(self, v: str):
        self.stage_filter = v or "All"
        self.page = 1

    def set_brain_filter(self, v: str):
        if not v or v == "All":
            self.brain_filter_key = "All"
        else:
            self.brain_filter_key = BRAIN_NAME_TO_KEY.get(v, "All")
        self.page = 1

    @rx.var
    def filtered_rows(self) -> list[dict]:
        q = (self.search_project or "").strip().lower()
        sf = self.stage_filter
        bf = self.brain_filter_key

        def match(row: dict) -> bool:
            if row["line_name"] in self.cancelled_line_names:
                return False
            ok_q = True if not q else (q in row["project_name"].lower())
            ok_s = (sf == "All") or (row["stage"] == sf)
            ok_b = (bf == "All") or (row["brain"] == bf)
            return ok_q and ok_s and ok_b

        return [r for r in INPROGRESS_DUMMY if match(r)]

    @rx.var
    def total_count(self) -> int:
        return len(self.filtered_rows)

    @rx.var
    def total_pages(self) -> int:
        rpp = self.rows_per_page
        if rpp <= 0:
            return 1
        pages, rem = divmod(len(self.filtered_rows), rpp)
        return pages + (1 if rem else 0) or 1

    @rx.var
    def page_clamped(self) -> int:
        if self.page < 1:
            return 1
        if self.page > self.total_pages:
            return self.total_pages
        return self.page

    @rx.var
    def paged_rows(self) -> list[dict]:
        p = self.page_clamped
        rpp = self.rows_per_page
        start = (p - 1) * rpp
        end = start + rpp
        return self.filtered_rows[start:end]

    @rx.var
    def page_label(self) -> str:
        return f"Page {self.page_clamped} of {self.total_pages}"

    @rx.event
    def next_page(self):
        self.page = min(self.page + 1, self.total_pages)

    @rx.event
    def prev_page(self):
        self.page = max(1, self.page - 1)

    @rx.event
    def clear_filters(self):
        self.search_project = ""
        self.stage_filter = "All"
        self.brain_filter_key = "All"
        self.page = 1

    # Cancel flow
    @rx.event
    def ask_cancel(self, line_name: str):
        self.pending_cancel_line = line_name
        self.confirm_open = True

    @rx.event
    def cancel_cancel(self):
        self.confirm_open = False
        self.pending_cancel_line = ""

    @rx.event
    def confirm_cancel(self):
        if self.pending_cancel_line and self.pending_cancel_line not in self.cancelled_line_names:
            self.cancelled_line_names = [*self.cancelled_line_names, self.pending_cancel_line]
        self.pending_cancel_line = ""
        self.confirm_open = False


def _labeled(label: str, control: rx.Component) -> rx.Component:
    return rx.hstack(
        rx.text(label, size="2", color="var(--gray-11)"),
        control,
        gap="6px",
        align="center",
    )

def _filters() -> rx.Component:
    return rx.hstack(
        rx.text("Filters", weight="bold", color="var(--gray-12)"),

        _labeled(
            "Project Name",
            rx.input(
                placeholder="Project name…",
                value=LinesProgressState.search_project,
                on_change=LinesProgressState.set_search_project,
                size="2",
                style={"minWidth": "220px"},
            ),
        ),
        _labeled(
            "Stage",
            rx.select(
                LinesProgressState.stage_options,
                placeholder="Stage",
                value=LinesProgressState.stage_filter,
                on_change=LinesProgressState.set_stage_filter,
                size="2",
                style={"minWidth": "180px"},
            ),
        ),
        _labeled(
            "Brain Type",
            rx.select(
                LinesProgressState.brain_name_options,
                placeholder="Brain",
                value=rx.cond(LinesProgressState.brain_filter_key == "All", "All",
                              BRAIN_KEY_TO_NAME.get(LinesProgressState.brain_filter_key, "All")),
                on_change=LinesProgressState.set_brain_filter,
                size="2",
                style={"minWidth": "220px"},
            ),
        ),

        rx.spacer(),
        rx.button("Clear", variant="soft", on_click=LinesProgressState.clear_filters, size="2"),

        spacing="4",
        align="center",
        width="100%",
        wrap="nowrap",
        padding="8px 12px",
        border="1px solid rgba(0,0,0,.06)",
        border_radius="10px",
        bg="rgba(2,6,23,.02)",
    )

def _actions_menu(row: Dict) -> rx.Component:
    return rx.dropdown_menu.root(
        rx.dropdown_menu.trigger(
            rx.button(rx.icon("ellipsis"), variant="ghost", size="1", padding="0 6px"),
        ),
        rx.dropdown_menu.content(
            rx.dropdown_menu.item(
                "Cancel…",
                on_click=lambda ln=row["line_name"]: LinesProgressState.ask_cancel(ln),
            ),
        ),
    )

def _progress_cell(pct: int) -> rx.Component:
    return rx.vstack(
        rx.progress(value=pct, max=100, width="160px"),
        rx.text(f"{pct}%", size="1", color="var(--gray-11)"),
        spacing="1",
        align="start",
    )

def _table() -> rx.Component:
    header = rx.table.header(
        rx.table.row(
            rx.table.column_header_cell("Project"),
            rx.table.column_header_cell("Line"),
            rx.table.column_header_cell("Location"),
            rx.table.column_header_cell("Brain"),
            rx.table.column_header_cell("Stage"),
            rx.table.column_header_cell("Progress"),
            rx.table.column_header_cell("Updated"),
            rx.table.column_header_cell("ETA"),
            rx.table.column_header_cell(""),  # actions
        )
    )

    body = rx.table.body(
        rx.foreach(
            LinesProgressState.paged_rows,
            lambda row: rx.table.row(
                rx.table.cell(row["project_name"]),
                rx.table.cell(row["line_name"]),
                rx.table.cell(row["location"]),
                rx.table.cell(rx.badge(BRAIN_KEY_TO_NAME.get(row["brain"], row["brain"]))),
                rx.table.cell(rx.badge(row["stage"], variant="soft")),
                rx.table.cell(_progress_cell(row["progress"])),
                rx.table.cell(row["updated_at"]),
                rx.table.cell(row["eta"]),
                rx.table.cell(_actions_menu(row)),
            ),
        )
    )

    return rx.card(
        rx.table.root(header, body, width="100%"),
        width="100%",
        padding="16px",
        radius="12px",
    )

def _pagination() -> rx.Component:
    return rx.hstack(
        rx.text(LinesProgressState.page_label),
        rx.spacer(),
        rx.hstack(
            rx.button("Prev", variant="soft", on_click=LinesProgressState.prev_page, disabled=(LinesProgressState.page_clamped <= 1)),
            rx.button("Next", variant="soft", on_click=LinesProgressState.next_page, disabled=(LinesProgressState.page_clamped >= LinesProgressState.total_pages)),
            spacing="2",
        ),
        align="center",
        width="100%",
        padding_top="8px",
    )

def _cancel_alert() -> rx.Component:
    return rx.alert_dialog.root(
        rx.alert_dialog.content(
            rx.alert_dialog.title("Cancel in-progress line?"),
            rx.alert_dialog.description(
                rx.text(
                    rx.cond(
                        LinesProgressState.pending_cancel_line != "",
                        "Are you sure you want to cancel '" + LinesProgressState.pending_cancel_line + "'?",
                        "Are you sure you want to cancel this line?",
                    )
                )
            ),
            rx.hstack(
                rx.alert_dialog.cancel(
                    rx.button("Back", variant="soft", on_click=LinesProgressState.cancel_cancel)
                ),
                rx.alert_dialog.action(
                    rx.button("Cancel Line", color_scheme="red", on_click=LinesProgressState.confirm_cancel)
                ),
                justify="end",
                gap="8px",
                width="100%",
                margin_top="12px",
            ),
            width="min(520px, 92vw)",
        ),
        open=LinesProgressState.confirm_open,
    )

def neuroforge_lines_in_progress() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text("Lines in Progress", size="6", weight="bold"),
                rx.spacer(),
                rx.badge(f"{LinesProgressState.total_count} total"),
                width="100%",
                align="center",
            ),
            _filters(),
            _table(),
            _pagination(),
            _cancel_alert(),
            spacing="4",
            width="min(1200px, 96vw)",
        ),
        padding="24px",
        min_height="100vh",
        display="flex",
        align_items="flex-start",
        justify_content="center",
    )
