import reflex as rx
from typing import List, Callable, Optional, Dict

# Status badge color mapping
STATUS_COLORS = {
    "online": "#10B981",      # Green
    "offline": "#EF4444",     # Red
    "maintenance": "#F59E0B", # Amber
    "unknown": "#6B7280",     # Gray
}

CARD_VARIANT = {
    "background": "#fff",
    "border_radius": "0.5rem",
    "box_shadow": "0 4px 6px rgba(0,0,0,0.08)",
    "padding": "1rem",
    "transition": "all 0.2s ease-in-out",
    "min_width": "260px",
    "max_width": "320px",
    "margin": "0.5rem",
}


def status_badge(status: str) -> rx.Component:
    """Status badge for camera state."""
    color = STATUS_COLORS.get(status.lower(), STATUS_COLORS["unknown"])
    label = status.upper()
    return rx.box(
        rx.text(label, color="#fff", font_size="0.75rem", font_weight="600"),
        background=color,
        border_radius="0.5rem",
        padding_x="0.75em",
        padding_y="0.25em",
        display="inline-block",
        margin_bottom="0.5em",
    )


def CameraCard(
    name: str,
    backend: str,
    status: str,
    on_select: Callable[[], None],
    on_configure: Optional[Callable[[], None]] = None,
    on_capture: Optional[Callable[[], None]] = None,
    on_diagnostics: Optional[Callable[[], None]] = None,
) -> rx.Component:
    """
    Card for a single camera with status, backend, and quick actions.
    """
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text("📷", font_size="1.5rem"),
                rx.text(name, font_weight="600", font_size="1.1rem"),
                spacing="2",
            ),
            rx.text(f"{backend} Camera", color="#6B7280", font_size="0.95rem"),
            status_badge(status),
            rx.hstack(
                rx.button(
                    "Select",
                    on_click=on_select or rx.noop,
                    variant="solid",
                    color_scheme="blue",
                    size="1",
                ),
                rx.button(
                    "Configure",
                    on_click=on_configure or rx.noop,
                    variant="surface",
                    color_scheme="gray",
                    size="1",
                ),
                rx.button(
                    "Capture",
                    on_click=on_capture or rx.noop,
                    variant="surface",
                    color_scheme="green",
                    size="1",
                ),
                rx.button(
                    "Diagnostics",
                    on_click=on_diagnostics or rx.noop,
                    variant="surface",
                    color_scheme="orange",
                    size="1",
                ),
                spacing="2",
            ),
            spacing="2",
            align="start",
        ),
        **CARD_VARIANT,
    )


def CameraList(
    cameras: List[Dict],
    on_select: Optional[Callable[[str], None]] = None,
    on_configure: Optional[Callable[[str], None]] = None,
    on_capture: Optional[Callable[[str], None]] = None,
    on_diagnostics: Optional[Callable[[str], None]] = None,
) -> rx.Component:
    """
    Grid/list of CameraCards.
    cameras: List of dicts with keys: name, backend, status
    """
    # For UI draft, use rx.noop for all event handlers
    return rx.box(
        rx.hstack(
            *[
                CameraCard(
                    name=cam["name"],
                    backend=cam.get("backend", "Unknown"),
                    status=cam.get("status", "unknown"),
                    on_select=(lambda n=cam["name"]: on_select(n)) if on_select else rx.noop,
                    on_configure=(lambda n=cam["name"]: on_configure(n)) if on_configure else rx.noop,
                    on_capture=(lambda n=cam["name"]: on_capture(n)) if on_capture else rx.noop,
                    on_diagnostics=(lambda n=cam["name"]: on_diagnostics(n)) if on_diagnostics else rx.noop,
                )
                for cam in cameras
            ],
            wrap="wrap",
            spacing="2",
            align="start",
        ),
        width="100%",
        padding="1rem 0",
    )


def CameraConfigForm(
    config: Dict,
    on_change: Callable[[str, any], None],
    on_submit: Callable[[], None],
    pixel_formats: Optional[List[str]] = None,
    trigger_modes: Optional[List[str]] = None,
    white_balance_modes: Optional[List[str]] = None,
) -> rx.Component:
    """
    Form for editing camera configuration.
    Args:
        config: Current config values (dict)
        on_change: Callback(field, value) for field changes
        on_submit: Callback for form submit
        pixel_formats: List of available pixel formats
        trigger_modes: List of available trigger modes
        white_balance_modes: List of available white balance modes
    """
    pixel_formats = pixel_formats or ["BGR8", "Mono8", "RGB8"]
    trigger_modes = trigger_modes or ["continuous", "trigger"]
    white_balance_modes = white_balance_modes or ["auto", "once", "off"]

    roi = config.get("roi", [0, 0, 1920, 1080])
    # Defensive: ensure roi is a list, not a Var or dict
    if isinstance(roi, dict):
        roi = [roi.get("x", 0), roi.get("y", 0), roi.get("width", 1920), roi.get("height", 1080)]
    elif not isinstance(roi, list):
        roi = [0, 0, 1920, 1080]

    return rx.form(
        rx.vstack(
            rx.text("Camera Configuration", font_weight="600", font_size="1.1rem", margin_bottom="0.5em"),
            rx.hstack(
                rx.input(
                    type="number",
                    value=config.get("exposure", ""),
                    placeholder="Exposure (μs)",
                    on_change=rx.noop,
                    width="120px",
                ),
                rx.input(
                    type="number",
                    value=config.get("gain", ""),
                    placeholder="Gain",
                    on_change=rx.noop,
                    width="100px",
                ),
                spacing="3",
            ),
            rx.hstack(
                rx.input(
                    type="number",
                    value=roi[0],
                    placeholder="ROI X",
                    on_change=rx.noop,
                    width="80px",
                ),
                rx.input(
                    type="number",
                    value=roi[1],
                    placeholder="ROI Y",
                    on_change=rx.noop,
                    width="80px",
                ),
                rx.input(
                    type="number",
                    value=roi[2],
                    placeholder="ROI Width",
                    on_change=rx.noop,
                    width="100px",
                ),
                rx.input(
                    type="number",
                    value=roi[3],
                    placeholder="ROI Height",
                    on_change=rx.noop,
                    width="100px",
                ),
                spacing="2",
            ),
            rx.hstack(
                rx.select(
                    pixel_formats,
                    value=config.get("pixel_format", pixel_formats[0]),
                    on_change=rx.noop,
                    placeholder="Pixel Format",
                    width="140px",
                ),
                rx.select(
                    trigger_modes,
                    value=config.get("trigger_mode", trigger_modes[0]),
                    on_change=rx.noop,
                    placeholder="Trigger Mode",
                    width="140px",
                ),
                rx.select(
                    white_balance_modes,
                    value=config.get("white_balance", white_balance_modes[0]),
                    on_change=rx.noop,
                    placeholder="White Balance",
                    width="140px",
                ),
                spacing="2",
            ),
            rx.hstack(
                rx.checkbox(
                    checked=config.get("image_enhancement", False),
                    on_change=rx.noop,
                ),
                rx.text("Image Enhancement", font_size="0.95rem"),
                spacing="2",
                align="center",
            ),
            rx.button(
                "Save / Apply",
                type="submit",
                variant="solid",
                color_scheme="blue",
                width="160px",
                margin_top="1em",
                on_click=on_submit,
            ),
            spacing="3",
            align="start",
        ),
        style={"width": "100%", "max_width": "480px", "background": "#fff", "border_radius": "0.5rem", "box_shadow": "0 1px 3px rgba(0,0,0,0.08)", "padding": "1.5rem"},
    )


def ImportExportButtons(
    on_import: Callable[[], None],
    on_export: Callable[[], None],
    import_loading: bool = False,
    export_loading: bool = False,
) -> rx.Component:
    """
    Buttons for importing and exporting camera configuration.
    """
    return rx.hstack(
        rx.button(
            "Import Config",
            on_click=on_import,
            variant="surface",
            color_scheme="gray",
            size="1",
            is_loading=import_loading,
        ),
        rx.button(
            "Export Config",
            on_click=on_export,
            variant="surface",
            color_scheme="blue",
            size="1",
            is_loading=export_loading,
        ),
        spacing="3",
    )


def CaptureButton(
    on_capture: Callable[[], None],
    loading: bool = False,
) -> rx.Component:
    """
    Button to trigger image capture.
    """
    return rx.button(
        "Capture Image",
        on_click=on_capture,
        variant="solid",
        color_scheme="green",
        size="2",
        is_loading=loading,
        width="180px",
        margin_top="1em",
    )


def DiagnosticsPanel(
    diagnostics: Dict,
) -> rx.Component:
    """
    Panel to display diagnostics/status info for a camera.
    """
    items = diagnostics.items() if hasattr(diagnostics, 'items') else []
    return rx.cond(
        (items.length() > 0),
        rx.box(
            rx.text("Diagnostics", font_weight="600", font_size="1.1rem", margin_bottom="0.5em"),
            rx.vstack(
                rx.foreach(
                    items,
                    lambda pair: rx.hstack(
                        rx.text(pair[0], font_weight="500", color="#374151", width="160px"),
                        rx.text(pair[1], color="#374151"),
                        spacing="2",
                    ),
                ),
                spacing="1",
                align="start",
            ),
            style={"width": "100%", "max_width": "420px", "background": "#fff", "border_radius": "0.5rem", "box_shadow": "0 1px 3px rgba(0,0,0,0.08)", "padding": "1.2rem", "margin_top": "1em"},
        ),
        rx.box(rx.text("No diagnostics available.", color="#6B7280"), padding="1em")
    )


def CapturedImageDisplay(
    image_data: str,
    camera_name: str = "",
) -> rx.Component:
    """
    Display captured image with download option.
    """
    return rx.cond(
        image_data != "",
        rx.box(
            rx.text("Captured Image", font_weight="600", font_size="1.1rem", margin_bottom="0.5em"),
            rx.vstack(
                rx.image(
                    src=f"data:image/jpeg;base64,{image_data}",
                    width="100%",
                    max_width="400px",
                    height="auto",
                    border_radius="0.5rem",
                    box_shadow="0 2px 8px rgba(0,0,0,0.1)",
                ),
                rx.hstack(
                    rx.text(f"From: {camera_name}", font_size="0.9rem", color="#6B7280"),
                    rx.button(
                        "Download",
                        on_click=rx.download(
                            data=f"data:image/jpeg;base64,{image_data}",
                            filename=f"capture_{camera_name.replace(':', '_')}.jpg"
                        ),
                        variant="surface",
                        color_scheme="blue",
                        size="1",
                    ),
                    spacing="3",
                    justify="between",
                    width="100%",
                ),
                spacing="3",
                align="center",
            ),
            style={
                "width": "100%", 
                "max_width": "420px", 
                "background": "#fff", 
                "border_radius": "0.5rem", 
                "box_shadow": "0 1px 3px rgba(0,0,0,0.08)", 
                "padding": "1.2rem", 
                "margin_top": "1em"
            },
        ),
        rx.box()  # Empty box when no image
    )