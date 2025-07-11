import reflex as rx
from poseidon.state.camera import CameraState


def camera_config_modal(camera: str) -> rx.Component:
    """Modular camera configuration modal component with improved layout and value display."""

    # --- NEW: Sync config on open ---
    def on_open():
        info = CameraState.camera_info
        config = {
            "exposure": info.get("current_exposure", 20000),
            "gain": info.get("current_gain", 1.0),
            "width": info.get("width", ""),
            "height": info.get("height", ""),
            "pixel_format": info.get("pixel_format", "BGR8"),
            "mode": info.get("mode", "continuous"),
            "image_enhancement": info.get("image_enhancement", False),
        }
        CameraState.camera_config = config

    # ---
    def exposure_slider() -> rx.Component:
        """Exposure slider with min/max/current value display."""
        return rx.vstack(
            rx.hstack(
                rx.text("Exposure (μs)", font_size="0.95rem", font_weight="600", color="#374151"),
                rx.hstack(
                    rx.text("31", font_size="0.85rem", color="#6B7280"),
                    rx.text("–", font_size="0.85rem", color="#6B7280"),
                    rx.text("1000000", font_size="0.85rem", color="#6B7280"),
                    spacing="1",
                ),
                rx.text("Current:", font_size="0.85rem", color="#6B7280"),
                rx.cond(
                    CameraState.camera_config.get("exposure") != None,
                    rx.text(CameraState.camera_config.get("exposure"), font_size="0.85rem", color="#2563EB", font_weight="600"),
                    rx.text("N/A", font_size="0.85rem", color="#6B7280"),
                ),
                spacing="3", align="center", width="100%", justify="between",
            ),
            rx.slider(
                min_value=31,
                max_value=1000000,
                value=[CameraState.camera_config.get("exposure", 31)],
                on_change=lambda v: CameraState.update_config_value("exposure", v[0]),
                width="100%",
            ),
            spacing="2", align="start", width="100%",
        )

    def gain_slider() -> rx.Component:
        """Gain slider with min/max/current value display."""
        return rx.vstack(
            rx.hstack(
                rx.text("Gain", font_size="0.95rem", font_weight="600", color="#374151"),
                rx.hstack(
                    rx.text("0", font_size="0.85rem", color="#6B7280"),
                    rx.text("–", font_size="0.85rem", color="#6B7280"),
                    rx.text("24", font_size="0.85rem", color="#6B7280"),
                    spacing="1",
                ),
                rx.text("Current:", font_size="0.85rem", color="#6B7280"),
                rx.cond(
                    CameraState.camera_config.get("gain") != None,
                    rx.text(CameraState.camera_config.get("gain"), font_size="0.85rem", color="#2563EB", font_weight="600"),
                    rx.text("N/A", font_size="0.85rem", color="#6B7280"),
                ),
                spacing="3", align="center", width="100%", justify="between",
            ),
            rx.slider(
                min_value=0,
                max_value=24,
                value=[CameraState.camera_config.get("gain", 0)],
                on_change=lambda v: CameraState.update_config_value("gain", v[0]),
                width="100%",
            ),
            spacing="2", align="start", width="100%",
        )

    def resolution_inputs() -> rx.Component:
        """Resolution width and height inputs."""
        return rx.hstack(
            rx.vstack(
                rx.text("Width", font_size="0.95rem", font_weight="600", color="#374151"),
                rx.input(
                    placeholder="1920",
                    value=CameraState.camera_config.get("width", ""),
                    on_change=lambda value: CameraState.update_config_value("width", value),
                    border="1px solid #D1D5DB",
                    border_radius="6px",
                    padding="0.75rem",
                    _focus={"border_color": "#374151"},
                ),
                spacing="2",
                align="start",
                width="100%",
            ),
            rx.vstack(
                rx.text("Height", font_size="0.95rem", font_weight="600", color="#374151"),
                rx.input(
                    placeholder="1080",
                    value=CameraState.camera_config.get("height", ""),
                    on_change=lambda value: CameraState.update_config_value("height", value),
                    border="1px solid #D1D5DB",
                    border_radius="6px",
                    padding="0.75rem",
                    _focus={"border_color": "#374151"},
                ),
                spacing="2",
                align="start",
                width="100%",
            ),
            spacing="4",
            width="100%",
        )

    def format_dropdowns() -> rx.Component:
        """Pixel format and trigger mode dropdowns."""
        return rx.hstack(
            rx.vstack(
                rx.text("Pixel Format", font_size="0.95rem", font_weight="600", color="#374151"),
                rx.select(
                    ["BGR8", "RGB8", "MONO8", "MONO16"],
                    value=CameraState.camera_config.get("pixel_format", "BGR8"),
                    on_change=lambda value: CameraState.update_config_value("pixel_format", value),
                    border="1px solid #D1D5DB",
                    border_radius="6px",
                    padding="0.75rem",
                ),
                spacing="2",
                align="start",
                width="100%",
            ),
            rx.vstack(
                rx.text("Trigger Mode", font_size="0.95rem", font_weight="600", color="#374151"),
                rx.select(
                    ["continuous", "software", "hardware"],
                    value=CameraState.camera_config.get("mode", "continuous"),
                    on_change=lambda value: CameraState.update_config_value("mode", value),
                    border="1px solid #D1D5DB",
                    border_radius="6px",
                    padding="0.75rem",
                ),
                spacing="2",
                align="start",
                width="100%",
            ),
            spacing="4",
            width="100%",
        )

    def action_buttons() -> rx.Component:
        """Action buttons with loading states and improved spacing."""
        return rx.hstack(
            rx.dialog.close(
                rx.button(
                    "Cancel",
                    variant="surface",
                    color_scheme="gray",
                    cursor="pointer",
                )
            ),
            rx.cond(
                CameraState.is_loading,
                rx.spinner(size="2", color="#3B82F6"),
                rx.button(
                    "Save Configuration",
                    variant="solid",
                    color_scheme="blue",
                    cursor="pointer",
                    on_click=lambda: CameraState.update_camera_config(camera, CameraState.camera_config),
                )
            ),
            rx.cond(
                CameraState.capture_loading,
                rx.spinner(size="2", color="#059669"),
                rx.button(
                    "Capture Image",
                    variant="solid",
                    color_scheme="green",
                    cursor="pointer",
                    on_click=lambda: CameraState.capture_image(camera),
                )
            ),
            spacing="3",
            justify="end",
            width="100%",
        )

    def camera_header() -> rx.Component:
        """Header with camera image, name, and status."""
        return rx.hstack(
            rx.box(
                "📷",
                font_size="2rem",
                padding="0.75rem",
                background="#F9FAFB",
                border_radius="8px",
                border="1px solid #E5E7EB",
            ),
            rx.vstack(
                rx.text(
                    f"{camera}",
                    font_weight="700",
                    font_size="1.2rem",
                    color="#111827",
                ),
                rx.text(
                    CameraState.camera_status_badges.get(camera, "Unknown"),
                    font_size="0.95rem",
                    color="#6B7280",
                ),
                spacing="1",
                align="start",
            ),
            spacing="3",
            align="center",
            width="100%",
            padding="1rem",
            background="#F9FAFB",
            border_radius="8px",
            margin_bottom="1rem",
        )

    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                "Configure",
                variant="solid",
                color_scheme="green",
                size="2",
                width="100%",
                on_click=lambda name=camera: CameraState.open_camera_config(name),
            ),
        ),
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.text("Camera Configuration", size="6", weight="bold"),
                    rx.dialog.close(rx.icon(tag="x", size=20, cursor="pointer")),
                    width="100%",
                    align="center",
                    justify="between",
                ),
                camera_header(),
                exposure_slider(),
                gain_slider(),
                resolution_inputs(),
                format_dropdowns(),
                rx.hstack(
                    rx.checkbox(
                        checked=CameraState.camera_config.get("image_enhancement", False),
                        on_change=lambda value: CameraState.update_config_value("image_enhancement", value),
                        size="2",
                    ),
                    rx.text("Enable Image Enhancement", color="#374151", font_size="0.95rem", font_weight="600"),
                    spacing="2",
                    align="center",
                ),
                action_buttons(),
                spacing="5",
                align="stretch",
                width="100%",
            ),
            max_width="600px",
        ),
    ) 