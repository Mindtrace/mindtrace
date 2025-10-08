# poseidon/pages/neuroforge_lines.py
import reflex as rx
from typing import List, Dict

# ---- Brain options (filter + display) -----------------------------------------
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
BRAIN_NAME_TO_KEY = {b["name"]: b["key"] for b in BRAIN_OPTIONS}
BRAIN_KEY_TO_NAME = {b["key"]: b["name"] for b in BRAIN_OPTIONS}

# ---- Dummy deployed lines -----------------------------------------------------
LINES_DUMMY: List[Dict] = [
    {"project_name": "Widget A Launch", "line_name": "Line-Alpha",   "location": "Plant 1 / Bay A",
     "integrator": "ACME Integrations", "brain": "weld",           "zones": 4, "deployed_at": "2025-08-21 10:15", "status": "Deployed"},
    {"project_name": "Widget A Launch", "line_name": "Line-Beta",    "location": "Plant 1 / Bay B",
     "integrator": "",                  "brain": "laser_weld",     "zones": 6, "deployed_at": "2025-08-28 16:42", "status": "Deployed"},
    {"project_name": "Gizmo Refresh",   "line_name": "Line-Gamma",   "location": "Plant 2 / West",
     "integrator": "Northstar SI",      "brain": "bead",           "zones": 3, "deployed_at": "2025-09-03 09:05", "status": "Deployed"},
    {"project_name": "Gizmo Refresh",   "line_name": "Line-Delta",   "location": "Plant 2 / East",
     "integrator": "Northstar SI",      "brain": "paint",          "zones": 5, "deployed_at": "2025-09-12 13:50", "status": "Deployed"},
    {"project_name": "Bolt Program",    "line_name": "Line-Epsilon", "location": "Plant 3 / North",
     "integrator": "",                  "brain": "metal_forming",  "zones": 2, "deployed_at": "2025-09-19 08:20", "status": "Deployed"},
    {"project_name": "Bolt Program",    "line_name": "Line-Zeta",    "location": "Plant 3 / South",
     "integrator": "Orbit Systems",     "brain": "trim",           "zones": 7, "deployed_at": "2025-09-22 11:37", "status": "Deployed"},
    {"project_name": "Widget B Ramp",   "line_name": "Line-Eta",     "location": "Plant 4 / Assembly",
     "integrator": "Orbit Systems",     "brain": "gear_box",       "zones": 3, "deployed_at": "2025-09-25 10:10", "status": "Deployed"},
    {"project_name": "Widget B Ramp",   "line_name": "Line-Theta",   "location": "Plant 4 / Test",
     "integrator": "",                  "brain": "stitching",      "zones": 4, "deployed_at": "2025-09-27 15:22", "status": "Deployed"},
    {"project_name": "MegaMix Program", "line_name": "Line-Iota",    "location": "Plant 5 / North",
     "integrator": "ACME Integrations", "brain": "metal_stamping", "zones": 8, "deployed_at": "2025-09-28 09:01", "status": "Deployed"},
    {"project_name": "MegaMix Program", "line_name": "Line-Kappa",   "location": "Plant 5 / South",
     "integrator": "ACME Integrations", "brain": "weld",           "zones": 6, "deployed_at": "2025-09-29 17:44", "status": "Deployed"},
]

# ---- State --------------------------------------------------------------------
class LinesPageState(rx.State):
    # Filters
    search_project: str = ""
    brain_filter_key: str = "All"  # key or "All"
    location_filter: str = "All"

    # Pagination
    page: int = 1
    rows_per_page: int = 8

    # UI feedback
    last_action: str = ""

    # Delete confirmation
    confirm_open: bool = False
    pending_delete_line: str = ""
    deleted_line_names: List[str] = []

    @rx.var
    def brain_name_options(self) -> list[str]:
        return ["All"] + BRAIN_NAMES

    @rx.var
    def location_options(self) -> list[str]:
        locs = sorted(list({row["location"] for row in LINES_DUMMY}))
        return ["All"] + locs

    @rx.var
    def brain_filter_label(self) -> str:
        return "All" if self.brain_filter_key == "All" else BRAIN_KEY_TO_NAME.get(self.brain_filter_key, "All")

    @rx.var
    def filtered_rows(self) -> list[dict]:
        q = (self.search_project or "").strip().lower()
        bf = self.brain_filter_key
        lf = self.location_filter

        def match(row: dict) -> bool:
            if row["line_name"] in self.deleted_line_names:
                return False
            ok_q = True if not q else (q in row["project_name"].lower())
            ok_b = (bf == "All") or (row["brain"] == bf)
            ok_l = (lf == "All") or (row["location"] == lf)
            return ok_q and ok_b and ok_l

        return [r for r in LINES_DUMMY if match(r)]

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

    def set_search_project(self, v: str):
        self.search_project = v
        self.page = 1

    def set_brain_filter(self, v: str):
        if not v or v == "All":
            self.brain_filter_key = "All"
        else:
            self.brain_filter_key = BRAIN_NAME_TO_KEY.get(v, "All")
        self.page = 1

    def set_location_filter(self, v: str):
        self.location_filter = v or "All"
        self.page = 1

    @rx.event
    def next_page(self):
        self.page = min(self.page + 1, self.total_pages)

    @rx.event
    def prev_page(self):
        self.page = max(1, self.page - 1)

    @rx.event
    def clear_filters(self):
        self.search_project = ""
        self.brain_filter_key = "All"
        self.location_filter = "All"
        self.page = 1

    # Delete flow
    @rx.event
    def ask_delete(self, line_name: str):
        self.pending_delete_line = line_name
        self.confirm_open = True

    @rx.event
    def cancel_delete(self):
        self.confirm_open = False
        self.pending_delete_line = ""

    @rx.event
    def confirm_delete(self):
        if self.pending_delete_line and self.pending_delete_line not in self.deleted_line_names:
            self.deleted_line_names = [*self.deleted_line_names, self.pending_delete_line]
            self.last_action = f"Deleted '{self.pending_delete_line}' (demo)."
        self.pending_delete_line = ""
        self.confirm_open = False

    @rx.event
    def clear_action(self):
        self.last_action = ""


def _labeled(label: str, control: rx.Component) -> rx.Component:
    return rx.hstack(
        rx.text(label, size="2", color="var(--gray-11)"),
        control,
        gap="6px",
        align="center",
    )


def _filters() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("Filters", weight="bold", color="var(--gray-12)"),

            _labeled(
                "Project Name",
                rx.input(
                    placeholder="Project name…",
                    value=LinesPageState.search_project,
                    on_change=LinesPageState.set_search_project,
                    size="2",
                    style={"minWidth": "220px"},
                ),
            ),
            _labeled(
                "Brain Type",
                rx.select(
                    LinesPageState.brain_name_options,
                    placeholder="Brain",
                    value=LinesPageState.brain_filter_label,
                    on_change=LinesPageState.set_brain_filter,
                    size="2",
                    style={"minWidth": "220px"},
                ),
            ),
            _labeled(
                "Location",
                rx.select(
                    LinesPageState.location_options,
                    placeholder="Location",
                    value=LinesPageState.location_filter,
                    on_change=LinesPageState.set_location_filter,
                    size="2",
                    style={"minWidth": "240px"},
                ),
            ),

            rx.spacer(),
            rx.button("Clear", variant="soft", on_click=LinesPageState.clear_filters, size="2"),
            spacing="4",
            align="center",
            width="100%",
            wrap="nowrap",
            padding="8px 12px",
            border="1px solid rgba(0,0,0,.06)",
            border_radius="10px",
            bg="rgba(2,6,23,.02)",
        ),
        rx.cond(
            LinesPageState.last_action != "",
            rx.callout(
                rx.hstack(
                    rx.text(LinesPageState.last_action),
                    rx.spacer(),
                    rx.button("Dismiss", size="1", variant="soft", on_click=LinesPageState.clear_action),
                    align="center",
                ),
                icon="info",
                color_scheme="blue",
            ),
            rx.fragment(),
        ),
        gap="10px",
        width="100%",
    )


def _actions_menu(row: Dict) -> rx.Component:
    return rx.dropdown_menu.root(
        rx.dropdown_menu.trigger(
            rx.button(rx.icon("ellipsis"), variant="ghost", size="1", padding="0 6px"),
        ),
        rx.dropdown_menu.content(
            rx.dropdown_menu.item(
                "Delete…",
                on_click=lambda ln=row["line_name"]: LinesPageState.ask_delete(ln),
            ),
        ),
    )


def _table() -> rx.Component:
    header = rx.table.header(
        rx.table.row(
            rx.table.column_header_cell("Project"),
            rx.table.column_header_cell("Line"),
            rx.table.column_header_cell("Location"),
            rx.table.column_header_cell("Integrator"),
            rx.table.column_header_cell("Brain"),
            rx.table.column_header_cell("Zones"),
            rx.table.column_header_cell("Deployed At"),
            rx.table.column_header_cell("Status"),
            rx.table.column_header_cell(""),  # empty header for actions column
        )
    )

    body = rx.table.body(
        rx.foreach(
            LinesPageState.paged_rows,
            lambda row: rx.table.row(
                rx.table.cell(row["project_name"]),
                rx.table.cell(row["line_name"]),
                rx.table.cell(row["location"]),
                rx.table.cell(rx.cond(row["integrator"] != "", row["integrator"], "—")),
                rx.table.cell(rx.badge(BRAIN_KEY_TO_NAME.get(row["brain"], row["brain"]))),
                rx.table.cell(row["zones"]),
                rx.table.cell(row["deployed_at"]),
                rx.table.cell(rx.badge("Deployed", color_scheme="green")),
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
        rx.text(LinesPageState.page_label),
        rx.spacer(),
        rx.hstack(
            rx.button("Prev", variant="soft", on_click=LinesPageState.prev_page, disabled=(LinesPageState.page_clamped <= 1)),
            rx.button("Next", variant="soft", on_click=LinesPageState.next_page, disabled=(LinesPageState.page_clamped >= LinesPageState.total_pages)),
            spacing="2",
        ),
        align="center",
        width="100%",
        padding_top="8px",
    )


def _delete_alert() -> rx.Component:
    return rx.alert_dialog.root(
        rx.alert_dialog.content(
            rx.alert_dialog.title("Delete line?"),
            rx.alert_dialog.description(
                rx.text(
                    rx.cond(
                        LinesPageState.pending_delete_line != "",
                        "Are you sure you want to delete '" + LinesPageState.pending_delete_line + "'? This action cannot be undone.",
                        "Are you sure you want to delete this line? This action cannot be undone.",
                    ),
                )
            ),
            rx.hstack(
                rx.alert_dialog.cancel(
                    rx.button("Cancel", variant="soft", on_click=LinesPageState.cancel_delete)
                ),
                rx.alert_dialog.action(
                    rx.button("Delete", color_scheme="red", on_click=LinesPageState.confirm_delete)
                ),
                justify="end",
                gap="8px",
                width="100%",
                margin_top="12px",
            ),
            width="min(520px, 92vw)",
        ),
        open=LinesPageState.confirm_open,   # keyword comes after the children
    )



def neuroforge_lines() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text("Deployed Lines", size="6", weight="bold"),
                rx.spacer(),
                rx.badge(f"{LinesPageState.total_count} total"),
                width="100%",
                align="center",
            ),
            _filters(),
            _table(),
            _pagination(),
            _delete_alert(),  # confirmation dialog lives at page root
            spacing="4",
            width="min(1200px, 96vw)",
        ),
        padding="24px",
        min_height="100vh",
        display="flex",
        align_items="flex-start",
        justify_content="center",
    )
