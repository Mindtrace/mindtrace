"""Camera configuration page with detailed controls."""

import reflex as rx
from ..state.camera_state import CameraState
from ..styles.theme import colors, spacing, radius

def camera_config_page() -> rx.Component:
    """Detailed camera configuration page."""
    
    def config_header() -> rx.Component:
        """Configuration page header."""
        return rx.vstack(
            rx.heading(
                "Camera Configuration",
                size="7",
                color=colors["gray_900"],
            ),
            rx.text(
                "Advanced camera parameter configuration and monitoring",
                color=colors["gray_600"],
                font_size="1.125rem",
            ),
            spacing=spacing["sm"],
            align="start",
            width="100%",
            padding_bottom=spacing["lg"],
            border_bottom=f"1px solid {colors['border']}",
        )
    
    def camera_selector() -> rx.Component:
        """Camera selection dropdown."""
        return rx.vstack(
            rx.text(
                "Select Camera",
                font_weight="500",
                color=colors["gray_700"],
            ),
            rx.select(
                CameraState.cameras,
                placeholder="Choose a camera...",
                value=CameraState.selected_camera,
                on_change=CameraState.set_selected_camera,
                size="3",
                width="100%",
            ),
            spacing=spacing["sm"],
            align="start",
            width="100%",
        )
    
    def camera_status_panel() -> rx.Component:
        """Camera status information panel."""
        return rx.cond(
            CameraState.selected_camera != "",
            rx.box(
                rx.vstack(
                    rx.text(
                        f"Status: {CameraState.selected_camera}",
                        font_weight="600",
                        color=colors["gray_900"],
                    ),
                    rx.text(
                        f"Current Status: {CameraState.camera_statuses.get(CameraState.selected_camera, 'Unknown')}",
                        color=colors["gray_600"],
                    ),
                    rx.divider(),
                    rx.text(
                        "Current Configuration:",
                        font_weight="500",
                        color=colors["gray_700"],
                    ),
                    rx.cond(
                        CameraState.camera_configs.get(CameraState.selected_camera, {}) != {},
                        rx.vstack(
                            rx.text(
                                f"Exposure: {CameraState.camera_configs.get(CameraState.selected_camera, {}).get('exposure_time', 'N/A')} μs",
                                font_size="0.875rem",
                                color=colors["gray_600"],
                            ),
                            rx.text(
                                f"Gain: {CameraState.camera_configs.get(CameraState.selected_camera, {}).get('gain', 'N/A')} dB",
                                font_size="0.875rem",
                                color=colors["gray_600"],
                            ),
                            rx.text(
                                f"Trigger Mode: {CameraState.camera_configs.get(CameraState.selected_camera, {}).get('trigger_mode', 'N/A')}",
                                font_size="0.875rem",
                                color=colors["gray_600"],
                            ),
                            spacing=spacing["xs"],
                            align="start",
                        ),
                        rx.text(
                            "No configuration data available",
                            font_size="0.875rem",
                            color=colors["gray_400"],
                            font_style="italic",
                        ),
                    ),
                    spacing=spacing["md"],
                    align="start",
                    width="100%",
                ),
                background=colors["white"],
                border=f"1px solid {colors['border']}",
                border_radius=radius["lg"],
                padding=spacing["lg"],
            ),
        )
    
    def action_panel() -> rx.Component:
        """Camera action buttons panel."""
        return rx.cond(
            CameraState.selected_camera != "",
            rx.box(
                rx.vstack(
                    rx.text(
                        "Camera Actions",
                        font_weight="600",
                        color=colors["gray_900"],
                        margin_bottom=spacing["md"],
                    ),
                    rx.vstack(
                        rx.button(
                            "Configure Camera",
                            size="3",
                            variant="solid",
                            color_scheme="blue",
                            width="100%",
                            on_click=CameraState.open_config_modal(CameraState.selected_camera),
                            disabled=rx.cond(
                                CameraState.camera_statuses.get(CameraState.selected_camera, "unknown") != "initialized",
                                True,
                                False,
                            ),
                        ),
                        rx.button(
                            "Capture Image",
                            size="3",
                            variant="outline",
                            width="100%",
                            on_click=lambda: CameraState.capture_image(CameraState.selected_camera),
                            disabled=rx.cond(
                                CameraState.camera_statuses.get(CameraState.selected_camera, "unknown") != "initialized",
                                True,
                                CameraState.capture_loading,
                            ),
                        ),
                        rx.button(
                            "Start Stream",
                            size="3",
                            variant="outline",
                            color_scheme="green",
                            width="100%",
                            on_click=lambda: CameraState.start_stream(CameraState.selected_camera),
                            disabled=(
                                (CameraState.camera_statuses.get(CameraState.selected_camera, "unknown") != "initialized") |
                                (CameraState.streaming_camera_name == CameraState.selected_camera)
                            ),
                        ),
                        spacing=spacing["md"],
                        width="100%",
                    ),
                    spacing=spacing["md"],
                    align="start",
                    width="100%",
                ),
                background=colors["white"],
                border=f"1px solid {colors['border']}",
                border_radius=radius["lg"],
                padding=spacing["lg"],
            ),
        )
    
    return rx.box(
        rx.container(
            rx.vstack(
                config_header(),
                camera_selector(),
                rx.grid(
                    camera_status_panel(),
                    action_panel(),
                    columns="2",
                    gap=spacing["xl"],
                    width="100%",
                ),
                spacing=spacing["xl"],
                width="100%",
            ),
            max_width="1200px",
            padding=spacing["xl"],
        ),
        background=colors["surface"],
        min_height="100vh",
        on_mount=CameraState.refresh_cameras,
    )