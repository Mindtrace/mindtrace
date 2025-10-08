import reflex as rx
from poseidon.state.neuroforge_create_line_state import CreateLineState, CreateLineFlowState

THINK_TANK_IMAGE = "/assets/brains/brain_bank.png"

BRAIN_OPTIONS = [
    {"key": "weld",            "name": "Weld Brain",           "desc": "Detects and analyzes weld defects with high precision."},
    {"key": "laser_weld",      "name": "Laser Weld Brain",     "desc": "Monitors laser welding quality for precision and consistency."},
    {"key": "bead",            "name": "Bead Brain",           "desc": "Analyzes bead formation, detects irregularities, and optimizes bead quality."},
    {"key": "paint",           "name": "Paint Brain",          "desc": "Evaluates paint quality: coating uniformity, drips, and inconsistencies."},
    {"key": "metal_forming",   "name": "Metal-Forming Brain",  "desc": "Detects deformations, cracks, and structural issues in forming processes."},
    {"key": "trim",            "name": "Trim Brain",           "desc": "Checks trim quality: clean cuts, alignment, and minimal defects."},
    {"key": "gear_box",        "name": "Gear-Box Brain",       "desc": "Analyzes gearbox components for wear, misalignment, and defects."},
    {"key": "stitching",       "name": "Stitching Brain",      "desc": "Inspects stitching in textiles/leather for durability and precision."},
    {"key": "metal_stamping",  "name": "Metal-Stamping Brain", "desc": "Finds stamping defects like misalignment, burrs, and incomplete impressions."},
]

# Soft themed accent per brain (feel free to tweak)
BRAIN_COLORS = {
    "weld": "#5B8CFF",
    "laser_weld": "#53D1B6",
    "bead": "#8B6CFF",
    "paint": "#52B6FF",
    "metal_forming": "#5FD6D0",
    "trim": "#8A4DFF",
    "gear_box": "#5ED1B2",
    "stitching": "#6C3BFF",
    "metal_stamping": "#5C73FF",
}

AVAILABLE_CAMERAS = [
    {"id": "CAM-1", "name": "Camera 1"},
    {"id": "CAM-2", "name": "Camera 2"},
    {"id": "CAM-3", "name": "Camera 3"},
    {"id": "CAM-4", "name": "Camera 4"},
    {"id": "CAM-5", "name": "Camera 5"},
    {"id": "CAM-6", "name": "Camera 6"},
]

LINE_LOCATIONS = ["Station A", "Station B", "Station C", "Station D"]
MODEL_OPTIONS = ["DefectNet-small", "DefectNet-base", "DefectNet-large"]

DUMMY_IMAGES = [
    # swap these with your backend URLs later
    "/test_1.png",
    "/test_1.png",
    "/test_1.png",
    "/test_1.png",
    "/test_1.png",
    "/test_1.png",
    "/test_1.png",
    "/test_1.png",
    "/test_1.png",
    "/test_1.png",
    "/test_1.png",
    "/test_1.png"
]


def _card(title: str, body: rx.Component, subtitle: str | None = None, max_width: str = "880px") -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.vstack(
                rx.text(title, weight="bold", size="5"),
                rx.cond(
                    subtitle is not None,
                    rx.text(subtitle, size="2", color="var(--gray-11)"),
                    rx.fragment(),
                ),
                spacing="2",
                width="100%",
            ),
            body,
            gap="14px",
            width="100%",
        ),
        padding="18px",
        radius="lg",
        width="100%",
        max_width=max_width,      # <= keep the form narrow
        margin_x="auto",          # <= center it
    )


def _field(label: str, control: rx.Component, hint: str | None = None) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text(label, size="2", color="var(--gray-12)", weight="medium"),
            rx.spacer(),
            align="center",
            width="100%",
        ),
        control,
        rx.cond(
            hint is not None,
            rx.text(hint, size="1", color="var(--gray-10)"),
            rx.fragment(),
        ),
        gap="6px",
        width="100%",
    )


def step_line_info() -> rx.Component:
    return _card(
        "Line Information",
        rx.vstack(
            # 2 equal columns on wide screens; collapses to 1 on small via minmax
            rx.grid(
                _field(
                    "Project name",
                    rx.input(
                        placeholder="e.g., Widget A Launch",
                        value=CreateLineState.project_name,
                        on_change=CreateLineState.set_project_name,
                        size="3",
                    ),
                ),
                _field(
                    "Line name",
                    rx.input(
                        placeholder="Line name",
                        value=CreateLineState.line_name,
                        on_change=CreateLineState.set_line_name,
                        size="3",
                    ),
                ),
                _field(
                    "Location / Plant / Area",
                    rx.input(
                        placeholder="Location / Plant / Area",
                        value=CreateLineState.location,
                        on_change=CreateLineState.set_location,
                        size="3",
                    ),
                ),
                _field(
                    "System integrator (optional)",
                    rx.input(
                        placeholder="System integrator",
                        value=CreateLineState.integrator,
                        on_change=CreateLineState.set_integrator,
                        size="3",
                    ),
                    hint="Company or team responsible for deployment (optional).",
                ),
                _field(
                    "Inspection zones",
                    rx.input(
                        type="number",
                        placeholder="0",
                        value=CreateLineState.inspection_zones_str,
                        on_change=CreateLineState.set_inspection_zones,
                        size="3",
                    ),
                    hint="How many distinct inspection regions exist on this line?",
                ),
                # responsive 2-col that still fills width neatly
                grid_template_columns="repeat(2, minmax(280px, 1fr))",
                gap="14px",
                width="100%",
            ),
            _field(
                "Description",
                rx.text_area(
                    placeholder="Purpose, part family, notes…",
                    value=CreateLineState.description,
                    on_change=CreateLineState.set_description,
                    rows="5",
                ),
            ),
            gap="16px",
            width="100%",
        ),
        subtitle="Provide basic metadata about the production line.",
        max_width="860px",
    )




class Step2LocalState(rx.State):
    hover_key: str = ""

    @rx.event
    def set_hover(self, key: str):
        self.hover_key = key

    @rx.event
    def clear_hover(self):
        self.hover_key = ""


def _pill(opt: dict) -> rx.Component:
    key = opt["key"]
    label = opt["name"]
    color = BRAIN_COLORS.get(key, "var(--accent-9)")
    is_sel = (CreateLineState.selected_brain == key)
    is_hover = (Step2LocalState.hover_key == key)
    active = is_sel | is_hover

    return rx.box(
        rx.hstack(
            rx.box(
                width="8px",
                height="8px",
                border_radius="9999px",
                background=color,
            ),
            rx.text(label, weight="medium"),
            spacing="3",
            align="center",
        ),
        padding="10px 14px",
        border_radius="9999px",
        border=rx.cond(active, f"2px solid {color}", "2px solid var(--gray-6)"),
        background=rx.cond(is_sel, f"color-mix(in oklab, {color} 16%, white)", "white"),
        box_shadow=rx.cond(active, "0 8px 24px rgba(0,0,0,.10)", "0 2px 8px rgba(0,0,0,.06)"),
        style={
            "cursor": "pointer",
            "transform": rx.cond(active, "translateY(-1px)", "translateY(0)"),
            "transition": "all .18s ease",
            "userSelect": "none",
            "whiteSpace": "nowrap",
        },
        on_click=lambda k=key: CreateLineState.select_brain(k),
        on_mouse_enter=lambda k=key: Step2LocalState.set_hover(k),
        on_mouse_leave=Step2LocalState.clear_hover,
    )


def _selected_details() -> rx.Component:
    # Render details for the currently selected brain without Python dict lookups on a Var
    return rx.vstack(
        *[
            rx.cond(
                CreateLineState.selected_brain == opt["key"],
                rx.vstack(
                    rx.hstack(
                        rx.text(opt["name"], size="5", weight="bold"),
                        rx.badge("Selected", variant="soft"),
                        spacing="4",
                        align="center",
                    ),
                    rx.text(opt["desc"], size="2", color="var(--gray-11)"),
                    spacing="3",
                    width="100%",
                ),
                rx.fragment(),
            )
            for opt in BRAIN_OPTIONS
        ],
        # If nothing selected yet, show a hint
        rx.cond(
            CreateLineState.selected_brain == "",
            rx.text("Choose a brain from the right to continue.", size="2", color="var(--gray-11)"),
            rx.fragment(),
        ),
        width="100%",
        gap="6px",
    )


def step_brain_selector() -> rx.Component:
    return rx.vstack(
        # Hero think-tank image banner
        # rx.card(
        #     rx.vstack(
        #         rx.image(
        #             src=THINK_TANK_IMAGE,
        #             width="100%",
        #             height="260px",
        #             object_fit="contain",
        #         ),
        #         rx.hstack(
        #             rx.text("Brain-Sense™ AI Brain Bank", size="5", weight="bold"),
        #             rx.spacer(),
        #             rx.badge("Pick one to continue", color_scheme="purple"),
        #             width="100%",
        #             align="center",
        #         ),
        #         spacing="4",
        #         width="100%",
        #     ),
        #     padding="14px",
        #     radius="lg",
        # ),
        rx.text("Brain-Sense™ AI Brain Bank", size="5", weight="bold"),

        rx.box(height="8px"),

        rx.grid(
            rx.card(
                _selected_details(),
                padding="16px",
                radius="lg",
                height="100%",
            ),
            # Right: pill grid
            rx.box(
                rx.text("Brains", size="3", weight="medium", margin_bottom="8px"),
                rx.box(
                    rx.grid(
                        *[_pill(o) for o in BRAIN_OPTIONS],
                        columns="repeat(auto-fit, minmax(220px, 1fr))",
                        gap="10px",
                        width="100%",
                    ),
                    padding="6px",
                ),
                width="100%",
            ),
            columns="minmax(260px, 1.2fr) minmax(320px, 2fr)",
            gap="16px",
            width="100%",
        ),
        gap="12px",
        width="100%",
    )


class Step3LocalState(rx.State):
    # modal context
    modal_open: bool = False
    editing_id: str = ""
    editing_name: str = ""

    # editing fields (dummy defaults)
    editing_trigger: str = "continuous"     # "continuous" | "trigger"
    editing_exposure: int = 158489          # μs
    editing_gain: int = 50                  # 0..48 demo
    editing_stream_on: bool = True

    # saved configs per camera (dummy persistence inside this step)
    saved_configs: dict[str, dict] = {}

    # transient success banner
    last_success: str = ""

    @rx.event
    def scan(self):
        # pretend we probed the network / SDK
        self.last_success = "Scan complete — cameras are up to date."
    
    @rx.event
    def refresh(self):
        # pretend we reloaded camera metadata/preview
        self.last_success = "Camera list refreshed."

    @rx.event
    def open_modal(self, cam_id: str, cam_name: str):
        self.editing_id = cam_id
        self.editing_name = cam_name
        cfg = self.saved_configs.get(cam_id, {})
        self.editing_trigger = cfg.get("trigger", "continuous")
        self.editing_exposure = int(cfg.get("exposure", 158489))
        self.editing_gain = int(cfg.get("gain", 50))
        self.editing_stream_on = bool(cfg.get("stream_on", True))
        self.modal_open = True

    @rx.event
    def close_modal(self):
        self.modal_open = False

    # setters for fields (string -> int coercion when needed)
    def set_trigger(self, mode: str): self.editing_trigger = mode
    def set_exposure(self, v: str):
        try:
            self.editing_exposure = max(10, min(1_000_000, int(v)))
        except Exception:
            self.editing_exposure = 10
    def set_gain(self, v: str):
        try:
            self.editing_gain = max(0, min(48, int(float(v))))
        except Exception:
            self.editing_gain = 0
    def toggle_stream(self):
        self.editing_stream_on = not self.editing_stream_on

    @rx.event
    def apply_config(self):
        # Save in local per-cam store
        self.saved_configs = {
            **self.saved_configs,
            self.editing_id: {
                "trigger": self.editing_trigger,
                "exposure": self.editing_exposure,
                "gain": self.editing_gain,
                "stream_on": self.editing_stream_on,
            },
        }
        self.last_success = f"Applied configuration to {self.editing_name} ({self.editing_id})"
        self.modal_open = False

    @rx.event
    def clear_success(self):
        self.last_success = ""


def _kv(label: str, value: rx.Component) -> rx.Component:
    return rx.hstack(
        rx.text(label, size="2", color="var(--gray-11)"),
        rx.spacer(),
        value,
        align="center",
        width="100%",
    )


def _slider_row(
    label: str, min_v: int, max_v: int, value_var, on_change, suffix: str = ""
) -> rx.Component:
    return rx.vstack(
        _kv(
            label,
            rx.text(
                rx.hstack(rx.text("Current:"), rx.text(value_var), rx.text(suffix)),
                size="2",
                color="var(--gray-11)",
            ),
        ),
        # HTML range input is robust with Reflex events
        rx.input(
            type="range",
            min=str(min_v),
            max=str(max_v),
            step="1",
            value=value_var,
            on_change=on_change,
            width="100%",
        ),
        spacing="2",
        width="100%",
    )

def _success_banner() -> rx.Component:
    return rx.cond(
        Step3LocalState.last_success != "",
        rx.card(
            rx.hstack(
                rx.icon("check-circle-2"),
                rx.text(Step3LocalState.last_success),
                rx.spacer(),
                rx.icon("x", cursor="pointer", on_click=Step3LocalState.clear_success),
                align="center",
                spacing="3",
                width="100%",
            ),
            padding="10px 12px",
            radius="md",
            style={
                "background": "var(--green-3)",
                "border": "1px solid var(--green-6)",
            },
        ),
        rx.fragment(),
    )


def _edit_modal() -> rx.Component:
    return rx.cond(
        Step3LocalState.modal_open,
        rx.box(
            # Backdrop
            rx.box(
                position="fixed",
                inset="0",
                bg="rgba(0,0,0,.35)",
                z_index="1000",
                on_click=Step3LocalState.close_modal,
            ),
            # Modal
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.text("Camera Configuration", weight="bold", size="5"),
                        rx.spacer(),
                        rx.icon("x", cursor="pointer", on_click=Step3LocalState.close_modal),
                        align="center",
                        width="100%",
                    ),
                    rx.card(
                        rx.hstack(
                            rx.hstack(
                                rx.box(
                                    rx.icon("camera"),
                                    width="40px",
                                    height="40px",
                                    border_radius="8px",
                                    bg="var(--gray-4)",
                                    display="flex",
                                    align_items="center",
                                    justify_content="center",
                                ),
                                rx.vstack(
                                    rx.text(Step3LocalState.editing_name, weight="medium"),
                                    rx.text(Step3LocalState.editing_id, size="1", color="var(--gray-11)"),
                                    spacing="1",
                                ),
                                spacing="3",
                                align="center",
                            ),
                            rx.badge("Configuration Access", color_scheme="green"),
                            justify="between",
                            width="100%",
                            align="center",
                        ),
                        padding="12px",
                        radius="md",
                    ),
                    # Trigger mode
                    rx.vstack(
                        _kv(
                            "Trigger Mode",
                            rx.text(
                                rx.hstack(
                                    rx.text("Current:"),
                                    rx.text(Step3LocalState.editing_trigger.capitalize()),
                                ),
                                size="2",
                                color="var(--gray-11)",
                            ),
                        ),
                        rx.hstack(
                            rx.button(
                                "Continuous",
                                variant=rx.cond(
                                    Step3LocalState.editing_trigger == "continuous",
                                    "solid",
                                    "soft",
                                ),
                                on_click=lambda: Step3LocalState.set_trigger("continuous"),
                            ),
                            rx.button(
                                "Trigger",
                                variant=rx.cond(
                                    Step3LocalState.editing_trigger == "trigger",
                                    "solid",
                                    "soft",
                                ),
                                on_click=lambda: Step3LocalState.set_trigger("trigger"),
                            ),
                            spacing="3",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    # Exposure & Gain
                    _slider_row(
                        "Exposure (μs)",
                        10,
                        1_000_000,
                        Step3LocalState.editing_exposure,
                        Step3LocalState.set_exposure,
                        suffix=" μs",
                    ),
                    _slider_row(
                        "Gain",
                        0,
                        48,
                        Step3LocalState.editing_gain,
                        Step3LocalState.set_gain,
                    ),
                    # Stream control
                    rx.button(
                        rx.cond(
                            Step3LocalState.editing_stream_on,
                            "Stop Stream",
                            "Start Stream",
                        ),
                        color_scheme=rx.cond(
                            Step3LocalState.editing_stream_on, "red", "green"
                        ),
                        variant="solid",
                        on_click=Step3LocalState.toggle_stream,
                        width="100%",
                    ),
                    # Preview (placeholder)
                    rx.box(
                        rx.box(
                            "Live preview",
                            position="absolute",
                            top="10px",
                            left="10px",
                            padding="4px 8px",
                            border_radius="9999px",
                            background="rgba(0,0,0,.6)",
                            color="white",
                            font_size="12px",
                        ),
                        bg="linear-gradient(135deg, #f2f4f8, #e9edf4)",
                        height="220px",
                        border_radius="12px",
                        border="1px solid var(--gray-6)",
                        position="relative",
                        overflow="hidden",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.button("Cancel", variant="soft", on_click=Step3LocalState.close_modal),
                        rx.spacer(),
                        rx.button("Apply Configuration", on_click=Step3LocalState.apply_config),
                        align="center",
                        width="100%",
                    ),
                    gap="12px",
                    width="100%",
                ),
                position="fixed",
                z_index="1001",
                top="50%",
                left="50%",
                transform="translate(-50%, -50%)",
                width="min(640px, 92vw)",
                bg="white",
                padding="16px",
                border_radius="12px",
                box_shadow="0 10px 30px rgba(0,0,0,.18)",
            ),
        ),
        rx.fragment(),
    )


# ---------- Step 3 UI (no selection; configure-only) ----------
def step_camera_config() -> rx.Component:
    def card_for(cam):
        cam_id = cam["id"]
        return rx.card(
            rx.vstack(
                rx.hstack(
                    rx.hstack(
                        rx.box(
                            rx.icon("camera"),
                            width="36px",
                            height="36px",
                            border_radius="8px",
                            bg="var(--gray-4)",
                            display="flex",
                            align_items="center",
                            justify_content="center",
                        ),
                        rx.vstack(
                            rx.text(cam["name"], weight="bold"),
                            rx.text(f"ID: {cam_id}", size="1", color="var(--gray-11)"),
                            spacing="1",
                        ),
                        spacing="3",
                        align="center",
                    ),
                    rx.badge("Online", color_scheme="green"),
                    justify="between",
                    width="100%",
                    align="center",
                ),
                rx.box(
                    bg="linear-gradient(135deg, #f5f7fb, #eef2f9)",
                    height="120px",
                    border_radius="10px",
                    border="1px solid var(--gray-6)",
                    width="100%",
                ),
                rx.hstack(
                    rx.spacer(),
                    rx.button("Configure", variant="outline",
                              on_click=lambda: Step3LocalState.open_modal(cam_id, cam["name"])),
                    align="center",
                    width="100%",
                ),
                gap="10px",
                width="100%",
            ),
            padding="12px",
            radius="lg",
        )

    return rx.vstack(
        _success_banner(),

        # Header row with title on the left and actions on the right
        rx.hstack(
            rx.text("Camera Configuration", size="4", weight="bold"),
            rx.spacer(),
            rx.hstack(
                rx.button("Scan",    variant="soft",    on_click=Step3LocalState.scan),
                rx.button("Refresh", variant="outline", on_click=Step3LocalState.refresh),
                spacing="3",
            ),
            align="center",
            width="100%",
        ),

        rx.grid(
            *[card_for(c) for c in AVAILABLE_CAMERAS],
            columns="repeat(auto-fit, minmax(320px, 1fr))",
            gap="12px",
            width="100%",
        ),
        _edit_modal(),
        gap="12px",
        width="100%",
    )



# ---------- Step 4: Map Zones → Cameras & Capture ----------
class Step4LocalState(rx.State):
    modal_open: bool = False
    modal_zone: str = ""
    tab: str = "count"          # "count" | "time"
    num_images: int = 50
    duration_min: int = 1
    capturing_zones: list[str] = []   # track which zones are capturing

    @rx.event
    def open_modal(self, zone: str):
        self.modal_zone = zone
        self.modal_open = True
        # sensible defaults each time
        self.tab = "count"
        self.num_images = 50
        self.duration_min = 1

    @rx.event
    def close_modal(self):
        self.modal_open = False

    def set_tab(self, v: str): self.tab = v

    def set_num_images(self, v: str):
        try:
            n = int(v) if v else 0
        except Exception:
            n = 0
        self.num_images = max(0, n)

    def set_duration_min(self, v: str):
        try:
            n = int(v) if v else 0
        except Exception:
            n = 0
        self.duration_min = max(0, n)

    @rx.event
    def confirm_capture(self):
        # mark this zone as capturing; close modal
        if self.modal_zone and (self.modal_zone not in self.capturing_zones):
            self.capturing_zones = [*self.capturing_zones, self.modal_zone]
        self.modal_open = False
    
    @rx.var
    def num_images_str(self) -> str:
        return str(self.num_images)

    @rx.var
    def duration_min_str(self) -> str:
        return str(self.duration_min)

def _capture_modal() -> rx.Component:
    return rx.cond(
        Step4LocalState.modal_open,
        rx.box(
            # Backdrop
            rx.box(
                position="fixed", inset="0", bg="rgba(0,0,0,.35)", z_index="1000",
                on_click=Step4LocalState.close_modal,
            ),
            # Modal card
            rx.box(
                rx.vstack(
                    # Header
                    rx.hstack(
                        rx.text("Initiate Capture", weight="bold", size="5"),
                        rx.spacer(),
                        rx.icon("x", cursor="pointer", on_click=Step4LocalState.close_modal),
                        align="center",
                        width="100%",
                    ),
                    # Zone + mapped camera info
                    rx.card(
                        rx.hstack(
                            rx.vstack(
                                rx.text(
                                    rx.cond(Step4LocalState.modal_zone != "", Step4LocalState.modal_zone, "Inspection Point"),
                                    weight="medium",
                                ),
                                rx.text(
                                    rx.cond(
                                        CreateLineState.zone_camera_map.get(Step4LocalState.modal_zone, "") != "",
                                        "Camera: " + CreateLineState.zone_camera_map.get(Step4LocalState.modal_zone, ""),
                                        "No camera selected",
                                    ),
                                    size="1",
                                    color="var(--gray-11)",
                                ),
                                spacing="1",
                            ),
                            rx.spacer(),
                            rx.badge("Ready"),
                            align="center",
                            width="100%",
                        ),
                        padding="10px", radius="md",
                    ),
                    # Body: vertical tabs
                    rx.hstack(
                        # Tabs (left)
                        rx.vstack(
                            rx.button(
                                "By count",
                                variant=rx.cond(Step4LocalState.tab == "count", "solid", "soft"),
                                on_click=lambda: Step4LocalState.set_tab("count"),
                                width="100%",
                            ),
                            rx.button(
                                "By time",
                                variant=rx.cond(Step4LocalState.tab == "time", "solid", "soft"),
                                on_click=lambda: Step4LocalState.set_tab("time"),
                                width="100%",
                            ),
                            gap="8px",
                            min_width="140px",
                        ),
                        # Panel (right)
                        rx.box(
                            rx.cond(
                                Step4LocalState.tab == "count",
                                rx.vstack(
                                    rx.text("Capture by number of images", weight="medium"),
                                    rx.text("Set how many images to acquire, then confirm to start.", size="1", color="var(--gray-11)"),
                                    rx.hstack(
                                        rx.text("Images:", size="2"),
                                        rx.input(
                                            type="number",
                                            value=Step4LocalState.num_images_str,
                                            on_change=Step4LocalState.set_num_images,
                                            min="0",
                                            width="120px",
                                        ),
                                        spacing="3",
                                        align="center",
                                    ),
                                    rx.hstack(
                                        rx.spacer(),
                                        rx.button("Confirm", on_click=Step4LocalState.confirm_capture),
                                        width="100%",
                                    ),
                                    gap="10px",
                                    width="100%",
                                ),
                                rx.vstack(
                                    rx.text("Capture by duration", weight="medium"),
                                    rx.text("Keep capturing until the time elapses, then stop.", size="1", color="var(--gray-11)"),
                                    rx.hstack(
                                        rx.text("Minutes:", size="2"),
                                        rx.input(
                                            type="number",
                                            value=Step4LocalState.duration_min_str,
                                            on_change=Step4LocalState.set_duration_min,
                                            min="0",
                                            width="120px",
                                        ),
                                        spacing="3",
                                        align="center",
                                    ),
                                    rx.hstack(
                                        rx.spacer(),
                                        rx.button("Confirm", on_click=Step4LocalState.confirm_capture),
                                        width="100%",
                                    ),
                                    gap="10px",
                                    width="100%",
                                ),
                            ),
                            flex="1",
                            padding="10px",
                            border="1px solid var(--gray-6)",
                            border_radius="10px",
                        ),
                        gap="12px",
                        width="100%",
                        align="start",
                    ),
                    gap="12px",
                    width="100%",
                ),
                position="fixed",
                z_index="1001",
                top="50%", left="50%",
                transform="translate(-50%, -50%)",
                width="min(680px, 92vw)",
                bg="white",
                padding="16px",
                border_radius="12px",
                box_shadow="0 10px 30px rgba(0,0,0,.18)",
            ),
        ),
        rx.fragment(),
    )

def step_data_capture_mapping() -> rx.Component:
    camera_ids = [c["id"] for c in AVAILABLE_CAMERAS]

    def row_for_zone(zone_label: str) -> rx.Component:
        current_cam = CreateLineState.zone_camera_map.get(zone_label, "")
        capture_disabled = (current_cam == "")

        is_capturing = Step4LocalState.capturing_zones.contains(zone_label)

        return rx.hstack(
            rx.box(
                rx.vstack(
                    rx.text(zone_label, weight="bold"),
                    rx.text(
                        rx.cond(
                            current_cam != "",
                            f"Camera: {current_cam}",
                            "No camera selected",
                        ),
                        size="1",
                        color="var(--gray-11)",
                    ),
                    spacing="2",
                ),
                min_width="220px",
            ),
            rx.select(
                camera_ids,
                placeholder="Choose camera…",
                value=current_cam,
                on_change=lambda v, z=zone_label: CreateLineState.map_zone_camera(z, v),
                style={"minWidth": "220px"},
            ),
            rx.button(
                rx.cond(
                    is_capturing,
                    rx.hstack(rx.spinner(size="2"), rx.text("Capturing initiated"), spacing="3", align="center"),
                    "Initiate capture",
                ),
                on_click=lambda z=zone_label: Step4LocalState.open_modal(z),
                disabled=capture_disabled,
                variant=rx.cond(is_capturing, "solid", "soft"),
            ),
            justify="between",
            align="center",
            width="100%",
            padding="8px 0",
        )

    return rx.vstack(
        rx.hstack(
            rx.text("Capture & Map", size="4", weight="bold"),
            rx.spacer(),
            rx.badge(
                rx.hstack(
                    rx.text("Inspection Points:"),
                    rx.text(CreateLineState.inspection_zones_str),
                    spacing="3",
                    align="center",
                )
            ),
            width="100%",
            align="center",
        ),
        rx.cond(
            CreateLineState.inspection_zones == 0,
            rx.callout(
                "No inspection zones configured. Go back to Step 1 and set the number of zones.",
                icon="info",
                color_scheme="gray",
            ),
            rx.vstack(
                rx.foreach(CreateLineState.zone_labels, lambda z: row_for_zone(z)),
                gap="6px",
                width="100%",
            ),
        ),
        _capture_modal(),  # modal for initiating capture
        gap="12px",
        width="100%",
    )

def step_image_grid_label() -> rx.Component:
    def tile(img_url: str):
        sel = CreateLineState.selected_images.contains(img_url)
        return rx.box(
            rx.box(
                rx.image(src=img_url, width="100%", height="180px", object_fit="cover", border_radius="10px"),
                rx.cond(
                    sel,
                    rx.box(
                        "✓",
                        position="absolute",
                        top="8px",
                        right="8px",
                        width="24px",
                        height="24px",
                        border_radius="9999px",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                        font_weight="700",
                        background="var(--accent-9)",
                        color="white",
                        box_shadow="0 2px 6px rgba(0,0,0,.15)",
                    ),
                    rx.fragment(),
                ),
                position="relative",
                width="100%",
            ),
            rx.hstack(
                rx.text("Image", size="1", color="var(--gray-11)"),
                rx.spacer(),
                rx.cond(sel, rx.badge("Selected"), rx.fragment()),
                align="center",
                width="100%",
                padding="6px 2px",
            ),
            on_click=lambda u=img_url: CreateLineState.toggle_image_select(u),
            cursor="pointer",
            padding="8px",
            border=rx.cond(sel, "2px solid var(--accent-8)", "1px solid var(--gray-6)"),
            border_radius="12px",
            transition="all .18s ease",
            _hover={"box_shadow": "0 8px 24px rgba(0,0,0,.08)", "transform": "translateY(-2px)"},
            width="100%",
        )

    total_const = len(DUMMY_IMAGES)

    return rx.vstack(
        # Header: title on left, selected + actions on right
        rx.hstack(
            rx.text("Image Gallery", size="4", weight="bold"),
            rx.spacer(),
            rx.badge(
                rx.hstack(
                    rx.text("Selected:"),
                    rx.text(CreateLineState.selected_images_count),
                    rx.text(" / "),
                    rx.text(str(total_const)),
                    align="center",
                    spacing="1",
                )
            ),
            rx.button(
                "Export ZIP",
                on_click=CreateLineState.export_selected_zip,
                disabled=(CreateLineState.selected_images.length() <= 0),
                variant="soft",
            ),
            rx.button(
                "Send for labeling",
                on_click=CreateLineState.send_to_label_studio,
                disabled=((CreateLineState.selected_images.length() <= 0) | (CreateLineState.sent_to_label_studio)),
            ),
            align="center",
            gap="10px",
            width="100%",
        ),

        # Feedback banners (optional)
        rx.cond(
            CreateLineState.exported_zip,
            rx.callout("Export prepared (dummy) for selected images.", icon="archive", color_scheme="blue"),
            rx.fragment(),
        ),
        rx.cond(
            CreateLineState.sent_to_label_studio,
            rx.callout("Send for labeling", icon="check", color_scheme="green"),
            rx.fragment(),
        ),

        # Responsive full-width grid
        rx.grid(
            *[tile(u) for u in DUMMY_IMAGES],
            columns="repeat(auto-fit, minmax(220px, 1fr))",
            min_child_width="280px",
            gap="14px",
            width="100%",
        ),

        gap="14px",
        width="100%",
    )

def _stat_card(title: str, value: str, subtitle: str | None = None) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.text(title, weight="bold"),
            rx.text(value, size="6", weight="bold"),
            rx.cond(
                subtitle is not None,
                rx.text(subtitle, size="1", color="var(--gray-11)"),
                rx.fragment(),
            ),
            spacing="6",
            align="start",
            width="100%",
        ),
        padding="16px",
        radius="lg",
        width="100%",
    )

def training_stats_cards() -> rx.Component:
    return rx.grid(
        _stat_card("Accuracy", "91%", "Top-1 on validation"),
        _stat_card("GPU Usage", "34%", "NVIDIA A5000 (demo)"),
        _stat_card("Images Processed", "12,480", "Total across all epochs"),
        _stat_card("Epochs", "20/20", "Completed"),
        columns="repeat(auto-fit, minmax(220px, 1fr))",
        gap="12px",
        width="100%",
    )



def step_model_training() -> rx.Component:
    running = (CreateLineState.training_status == "running")
    done    = (CreateLineState.training_status == "done")

    return rx.vstack(
        rx.text("Train Model", size="4", weight="bold"),

        rx.center(
            rx.button(
                rx.cond(
                    running,
                    rx.hstack(rx.spinner(size="2"), rx.text("Training…"), spacing="3", align="center"),
                    rx.text("Start Training"),
                ),
                on_click=CreateLineState.start_training_long,
                disabled=((CreateLineState.selected_images.length() <= 0) | running | done),
                size="3",
            ),
            width="100%",
            padding="8px 0",
        ),

        rx.cond(
            running | done,
            rx.vstack(
                rx.hstack(
                    rx.text("Progress"),
                    rx.spacer(),
                    rx.text(CreateLineState.training_progress_label, color="var(--gray-11)"),
                    align="center",
                    width="100%",
                ),
                rx.progress(value=CreateLineState.training_progress, max=100, width="100%"),
                gap="6px",
                width="100%",
            ),
            rx.fragment(),
        ),

        rx.cond(
            running | done,
            rx.box(
                rx.vstack(
                    rx.foreach(
                        CreateLineState.training_logs,
                        lambda line: rx.hstack(
                            rx.box(width="6px", height="6px", bg="var(--accent-9)", border_radius="9999px"),
                            rx.text(line, size="2"),
                            align="center",
                            gap="8px",
                        ),
                    ),
                    gap="8px",
                    width="100%",
                ),
                bg="var(--gray-2)",
                border="1px solid var(--gray-6)",
                border_radius="10px",
                padding="12px",
                max_height="260px",
                overflow_y="auto",
                width="100%",
            ),
            rx.fragment(),
        ),

        # inside step_model_training return stack:
        rx.cond(done, training_stats_cards(), rx.fragment()),
        gap="14px",
        width="100%",
    )




# --- Deploy: info sections + progress + button --------------------------------

DEPLOY_SECTIONS = [
    {
        "title": "Cloud Deployment",
        "icon": "cloud",
        "bullets": [
            "Easily scale and manage projects in different locations",
            "Reduce time to deploy without needing edge device configuration",
            "Quickly re-train models upon detecting performance changes",
        ],
    },
    {
        "title": "Edge Deployment",
        "icon": "cpu",
        "bullets": [
            "An all-in-one application for end-to-end AI deployment",
            "Seamless communication with industrial cameras & PLCs for real-time decisions",
            "In-app support for pre/post-processing scripts to manage images and outputs",
        ],
    },
    {
        "title": "Container Deployment",
        "icon": "package",  # lucide icon; swap to "server" / "box" if you prefer
        "bullets": [
            "Easily deploy models in self-hosted settings using Docker",
            "Run in Kubernetes",
            "Rapidly scale deployments (incl. NVIDIA Jetson devices)",
        ],
    },
]


def _deploy_card(title: str, icon: str, bullets: list[str]) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.box(
                    rx.icon(icon, size=22),
                    width="44px",
                    height="44px",
                    border_radius="12px",
                    bg="var(--accent-3)",
                    color="var(--accent-11)",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                ),
                rx.vstack(
                    rx.text(title, weight="medium", size="4"),
                    rx.text("Recommended uses & advantages", size="1", color="var(--gray-11)"),
                    spacing="1",
                ),
                align="center",
                spacing="3",
                width="100%",
            ),
            rx.vstack(
                *[
                    rx.hstack(
                        rx.icon("check", size=16, color="var(--green-10)"),
                        rx.text(point, size="2"),
                        align="start",
                        spacing="2",
                    )
                    for point in bullets
                ],
                spacing="3",
                width="100%",
            ),
            spacing="4",
            width="100%",
        ),
        padding="16px",
        radius="12px",
        width="100%",
        style={"boxShadow": "0 6px 18px rgba(0,0,0,.06)"},
    )


def step_deploy() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("Deploy Model", size="5", weight="medium"),
            rx.spacer(),
            # rx.badge(
            #     rx.hstack(
            #         rx.text("Model:"),
            #         rx.text(rx.cond(CreateLineState.selected_model != "", CreateLineState.selected_model, "Not selected")),
            #         spacing="2",
            #         align="center",
            #     ),
            # ),
            width="100%",
            align="center",
        ),

        rx.text(
            "Choose the approach that fits your environment. You can deploy the same trained model across multiple targets.",
            size="2",
            color="var(--gray-11)",
        ),

        rx.grid(
            *[
                _deploy_card(sec["title"], sec["icon"], sec["bullets"])
                for sec in DEPLOY_SECTIONS
            ],
            columns="repeat(auto-fit, minmax(280px, 1fr))",
            gap="12px",
            width="100%",
        ),

        rx.box(height="8px"),

        rx.cond(
            CreateLineFlowState.is_deploying,
            rx.vstack(
                rx.hstack(
                    rx.spinner(size="2"),
                    rx.text("Deploying…"),
                    rx.badge(CreateLineFlowState.deploy_progress_label),
                    spacing="4",
                    align="center",
                ),
                rx.progress(value=CreateLineFlowState.deploy_progress, max=100, width="100%"),
                spacing="3",
                width="100%",
            ),
            rx.fragment(),
        ),

        rx.hstack(
            rx.spacer(),
            rx.button(
                rx.cond(
                    CreateLineFlowState.is_deploying,
                    rx.hstack(rx.spinner(size="1"), rx.text("Deploying…"), spacing="3", align="center"),
                    rx.hstack(rx.icon("rocket"), rx.text("Deploy"), spacing="2", align="center"),
                ),
                on_click=CreateLineFlowState.deploy_with_progress,
                disabled=(CreateLineState.training_status != "done") | CreateLineFlowState.is_deploying,
                size="3",
            ),
            width="100%",
        ),

        rx.cond(
            CreateLineState.deploy_status == "deployed",
            rx.callout("Deployment successful!", icon="rocket", color_scheme="green"),
            rx.fragment(),
        ),

        spacing="4",
        width="100%",
    )


