import reflex as rx
from poseidon.state.camera import CameraState


def camera_config_modal() -> rx.Component:
    """Camera configuration modal with access control and project-aware functionality."""
    
    def exposure_slider() -> rx.Component:
        """Simple log-scale exposure slider using state Vars."""
        return rx.vstack(
            rx.hstack(
                rx.text("Exposure (μs)", font_size="0.95rem", font_weight="600", color="#374151"),
                rx.hstack(
                    rx.text(CameraState.exposure_min_value, font_size="0.85rem", color="#6B7280"),
                    rx.text("–", font_size="0.85rem", color="#6B7280"),
                    rx.text(CameraState.exposure_max_value, font_size="0.85rem", color="#6B7280"),
                    spacing="1",
                ),
                rx.text("Current:", font_size="0.85rem", color="#6B7280"),
                rx.text(CameraState.exposure_display_value, font_size="0.85rem", color="#2563EB", font_weight="600"),
                spacing="3", align="center", width="100%", justify="between",
            ),
            rx.slider(
                min_value=0,
                max_value=100,
                value=[CameraState.exposure_slider_value],
                on_change=lambda v: CameraState.set_exposure_from_slider(v[0]),
                width="100%",
                disabled=~CameraState.can_configure_selected,
            ),
            spacing="2", align="start", width="100%",
        )

    def gain_slider() -> rx.Component:
        """Gain slider with dynamic range and current value display."""
        ranges = CameraState.current_camera_ranges
        gain_range = ranges.get("gain", [0, 24])
        min_gain = rx.cond(gain_range.length() > 0, gain_range[0], 0)
        max_gain = rx.cond(gain_range.length() > 1, gain_range[1], 24)
        current_gain = CameraState.camera_config.get("gain", 0)
        return rx.vstack(
            rx.hstack(
                rx.text("Gain", font_size="0.95rem", font_weight="600", color="#374151"),
                rx.hstack(
                    rx.text(min_gain, font_size="0.85rem", color="#6B7280"),
                    rx.text("–", font_size="0.85rem", color="#6B7280"),
                    rx.text(max_gain, font_size="0.85rem", color="#6B7280"),
                    spacing="1",
                ),
                rx.text("Current:", font_size="0.85rem", color="#6B7280"),
                rx.text(current_gain, font_size="0.85rem", color="#2563EB", font_weight="600"),
                spacing="3", align="center", width="100%", justify="between",
            ),
            rx.slider(
                min_value=min_gain,
                max_value=max_gain,
                value=[current_gain],
                on_change=lambda v: CameraState.update_config_value("gain", v[0]),
                width="100%",
                disabled=~CameraState.can_configure_selected,
            ),
            spacing="2", align="start", width="100%",
        )

    def trigger_mode_selector() -> rx.Component:
        """Selector for camera trigger mode (continuous/trigger)."""
        current_mode = CameraState.camera_config.get("trigger_mode", "continuous")
        can_configure = CameraState.can_configure_selected
        
        return rx.vstack(
            rx.hstack(
                rx.text("Trigger Mode", font_size="0.95rem", font_weight="600", color="#374151"),
            rx.text(
            rx.cond(
                        current_mode == "continuous",
                        "Current: Continuous",
                        "Current: Trigger"
                    ),
                    font_size="0.85rem",
                    color="#2563EB",
                    font_weight="600",
                        ),
                spacing="3",
                        align="center",
                    width="100%",
                justify="between",
            ),
            rx.hstack(
                rx.button(
                    "Continuous",
                    variant=rx.cond(current_mode == "continuous", "solid", "outline"),
                    color_scheme="blue",
                    size="2",
                    on_click=lambda: CameraState.set_trigger_mode("continuous"),
                    width="100px",
                    disabled=~can_configure,
                ),
                rx.button(
                    "Trigger",
                    variant=rx.cond(current_mode == "trigger", "solid", "outline"),
                    color_scheme="blue",
                    size="2",
                    on_click=lambda: CameraState.set_trigger_mode("trigger"),
                    width="100px",
                    disabled=~can_configure,
                ),
                spacing="2",
                align="center",
            ),
            spacing="2",
            align="start",
            width="100%",
        )

    def camera_header() -> rx.Component:
        """Header with camera icon, name, project info, and access status."""
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
                    CameraState.selected_camera,
                    font_weight="700",
                    font_size="1.2rem",
                    color="#111827",
                ),
                rx.text(
                    f"Project: {CameraState.selected_project_name}",
                    font_size="0.9rem",
                    color="#6B7280",
                    font_style="italic",
                ),
                rx.cond(
                    CameraState.can_configure_selected,
                    rx.text(
                        "✓ Configuration Access",
                        font_size="0.85rem",
                        color="#059669",
                        font_weight="500",
                    ),
                    rx.text(
                        "⚠ Limited Access",
                        font_size="0.85rem",
                        color="#DC2626",
                        font_weight="500",
                    ),
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

    def stream_display() -> rx.Component:
        """Display the MJPEG stream if streaming is active."""
        return rx.cond(
            CameraState.is_streaming & CameraState.stream_url,
            rx.center(
                rx.box(
                    rx.image(
                        src=CameraState.stream_url,
                        width="100%",
                        max_width="480px",
                        max_height="360px",
                        border_radius="8px",
                        border="1px solid #E5E7EB",
                        alt="Live camera stream",
                        object_fit="contain",
                    ),
                    background="white",
                    padding="1rem",
                    border_radius="8px",
                    box_shadow="0 2px 4px rgba(0, 0, 0, 0.1)",
                    width="100%",
                ),
                width="100%",
            ),
            rx.center(
                rx.text(
                    rx.cond(
                        CameraState.can_configure_selected,
                        "Stream not started. Click 'Start Stream' to view live video.",
                        "Stream access requires project assignment. Contact your administrator.",
                    ),
                    font_size="0.95rem",
                    color="#6B7280",
                    text_align="center",
                ),
                padding="2rem",
                width="100%",
            ),
        )

    def stream_action_button() -> rx.Component:
        """Button to start or stop the MJPEG stream with access control."""
        can_stream = CameraState.can_configure_selected
        
        return rx.cond(
            can_stream,
            rx.cond(
                CameraState.is_streaming,
                rx.button(
                    "Stop Stream",
                    color_scheme="red",
                    on_click=CameraState.stop_stream,
                    width="100%",
                ),
                rx.button(
                    "Start Stream",
                    color_scheme="green",
                    on_click=lambda: CameraState.start_stream(CameraState.selected_camera),
                    width="100%",
                ),
            ),
            rx.button(
                "Stream Access Denied",
                color_scheme="gray",
                disabled=True,
                width="100%",
            ),
        )

    def action_buttons() -> rx.Component:
        """Action buttons with access control."""
        can_configure = CameraState.can_configure_selected
        
        return rx.hstack(
            rx.dialog.close(
                rx.button(
                    "Cancel",
                    variant="surface",
                    color_scheme="gray",
                    cursor="pointer",
                ),
            ),
            rx.cond(
                can_configure,
                rx.button(
                    "Apply Configuration",
                    variant="solid",
                    color_scheme="blue",
                    cursor="pointer",
                    on_click=CameraState.apply_config,
                ),
                rx.button(
                    "Access Denied",
                    variant="outline",
                    color_scheme="red",
                    disabled=True,
                    cursor="not-allowed",
                ),
            ),
            spacing="3",
            justify="end",
            width="100%",
        )

    def access_warning() -> rx.Component:
        """Warning message for limited access."""
        return rx.cond(
            ~CameraState.can_configure_selected,
            rx.box(
                rx.hstack(
                    rx.text("⚠", font_size="1.2rem", color="#DC2626"),
                    rx.vstack(
                        rx.text(
                            "Limited Access",
                            font_weight="600",
                            color="#DC2626",
                            font_size="0.9rem",
                        ),
                        rx.text(
                            "This camera is not assigned to your current project. Contact your administrator to request access.",
                            font_size="0.85rem",
                            color="#6B7280",
                        ),
                        spacing="1",
                        align="start",
                    ),
                    spacing="3",
                    align="start",
                ),
                padding="1rem",
                background="#FEF2F2",
                border="1px solid #FECACA",
                border_radius="8px",
                margin_bottom="1rem",
                width="100%",
            ),
        )

    return rx.dialog.root(
        rx.dialog.trigger(
            rx.box(),  # Invisible trigger - modal is controlled by state
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
                access_warning(),
                trigger_mode_selector(),
                exposure_slider(),
                gain_slider(),
                stream_action_button(),
                stream_display(),
                action_buttons(),
                spacing="4",
                align="stretch",
                width="100%",
            ),
            max_width="600px",
        ),
        open=CameraState.config_modal_open,
        on_open_change=lambda open: CameraState.set_config_modal_open(open),
    ) 