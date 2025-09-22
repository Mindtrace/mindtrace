"""Camera configuration modal component."""

import reflex as rx
from ..state.camera_state import CameraState
from ..styles.theme import colors, spacing, css_spacing, radius

def camera_modal() -> rx.Component:
    """Configuration modal for camera settings."""
    
    def modal_header() -> rx.Component:
        """Modal header with title and close button."""
        return rx.hstack(
            rx.heading(
                f"Configure {CameraState.selected_camera}",
                size="6",
                color=colors["gray_900"],
            ),
            rx.spacer(),
            rx.button(
                rx.icon("x"),
                variant="ghost",
                size="2",
                on_click=CameraState.close_config_modal,
            ),
            width="100%",
            align="center",
            padding_bottom=css_spacing["md"],
            border_bottom=f"1px solid {colors['border']}",
            margin_bottom=css_spacing["lg"],
        )
    
    def exposure_control() -> rx.Component:
        """Exposure time control."""
        return rx.vstack(
            rx.text(
                "Exposure Time (μs)",
                font_weight="500",
                color=colors["gray_700"],
            ),
            rx.input(
                type="number",
                value=CameraState.config_exposure,
                on_change=CameraState.set_config_exposure,
                min=rx.cond(
                    CameraState.config_ranges_for_selected.get("exposure", []).length() >= 2,
                    CameraState.config_ranges_for_selected.get("exposure", [])[0],
                    100
                ),
                max=rx.cond(
                    CameraState.config_ranges_for_selected.get("exposure", []).length() >= 2,
                    CameraState.config_ranges_for_selected.get("exposure", [])[1],
                    10000
                ),
                step=100,
                width="100%",
            ),
            rx.text(
                f"Current: {CameraState.config_exposure} μs",
                font_size="0.875rem",
                color=colors["gray_500"],
            ),
            spacing=spacing["sm"],
            align="start",
            width="100%",
        )
    
    def gain_control() -> rx.Component:
        """Gain control."""
        return rx.vstack(
            rx.text(
                "Gain (dB)",
                font_weight="500",
                color=colors["gray_700"],
            ),
            rx.input(
                type="number",
                value=CameraState.config_gain,
                on_change=CameraState.set_config_gain,
                min=rx.cond(
                    CameraState.config_ranges_for_selected.get("gain", []).length() >= 2,
                    CameraState.config_ranges_for_selected.get("gain", [])[0],
                    0
                ),
                max=rx.cond(
                    CameraState.config_ranges_for_selected.get("gain", []).length() >= 2,
                    CameraState.config_ranges_for_selected.get("gain", [])[1],
                    30
                ),
                step=1,
                width="100%",
            ),
            rx.text(
                f"Current: {CameraState.config_gain} dB",
                font_size="0.875rem",
                color=colors["gray_500"],
            ),
            spacing=spacing["sm"],
            align="start",
            width="100%",
        )
    
    def trigger_mode_control() -> rx.Component:
        """Trigger mode control."""
        return rx.vstack(
            rx.text(
                "Trigger Mode",
                font_weight="500",
                color=colors["gray_700"],
            ),
            rx.select(
                ["continuous", "trigger"],
                value=CameraState.config_trigger_mode,
                on_change=CameraState.set_config_trigger_mode,
                width="100%",
            ),
            rx.text(
                f"Current: {CameraState.config_trigger_mode}",
                font_size="0.875rem",
                color=colors["gray_500"],
            ),
            spacing=spacing["sm"],
            align="start",
            width="100%",
        )
    
    def modal_footer() -> rx.Component:
        """Modal footer with action buttons."""
        return rx.hstack(
            rx.button(
                "Cancel",
                variant="outline",
                size="3",
                on_click=CameraState.close_config_modal,
            ),
            rx.button(
                "Apply Configuration",
                variant="solid",
                size="3",
                color_scheme="blue",
                on_click=CameraState.apply_camera_config,
            ),
            spacing=spacing["md"],
            justify="end",
            width="100%",
            padding_top=css_spacing["lg"],
            border_top=f"1px solid {colors['border']}",
        )
    
    def parameter_ranges_info() -> rx.Component:
        """Display parameter ranges if available."""
        return rx.cond(
            CameraState.config_ranges_for_selected != {},
            rx.vstack(
                rx.text(
                    "Parameter Ranges",
                    font_weight="500",
                    color=colors["gray_700"],
                    margin_bottom=css_spacing["sm"],
                ),
                rx.vstack(
                    rx.cond(
                        CameraState.config_ranges_for_selected.get("exposure", []).length() >= 2,
                        rx.text(
                            f"Exposure: {CameraState.config_ranges_for_selected.get('exposure', [])[0]} - {CameraState.config_ranges_for_selected.get('exposure', [])[1]} μs",
                            font_size="0.75rem",
                            color=colors["gray_600"],
                        ),
                    ),
                    rx.cond(
                        CameraState.config_ranges_for_selected.get("gain", []).length() >= 2,
                        rx.text(
                            f"Gain: {CameraState.config_ranges_for_selected.get('gain', [])[0]} - {CameraState.config_ranges_for_selected.get('gain', [])[1]} dB",
                            font_size="0.75rem",
                            color=colors["gray_600"],
                        ),
                    ),
                    rx.cond(
                        CameraState.config_ranges_for_selected.get("trigger_modes", []).length() > 0,
                        rx.text(
                            f"Trigger Modes: {CameraState.config_ranges_for_selected.get('trigger_modes', [])}",
                            font_size="0.75rem",
                            color=colors["gray_600"],
                        ),
                    ),
                    spacing=spacing["xs"],
                    align="start",
                ),
                spacing=spacing["sm"],
                align="start",
                width="100%",
                padding=css_spacing["md"],
                background=colors["gray_50"],
                border_radius=radius["md"],
                border=f"1px solid {colors['border_light']}",
            ),
        )
    
    def modal_content() -> rx.Component:
        """Main modal content."""
        return rx.vstack(
            modal_header(),
            parameter_ranges_info(),
            rx.vstack(
                exposure_control(),
                gain_control(), 
                trigger_mode_control(),
                spacing=spacing["lg"],
                width="100%",
            ),
            modal_footer(),
            spacing=spacing["lg"],
            width="100%",
            max_width="500px",
        )
    
    return rx.dialog.root(
        rx.dialog.content(
            modal_content(),
            background=colors["white"],
            border_radius=radius["lg"],
            box_shadow="0 25px 50px -12px rgba(0, 0, 0, 0.25)",
            padding=css_spacing["xl"],
            max_width="500px",
            width="90vw",
        ),
        open=CameraState.config_modal_open,
    )

def status_banner() -> rx.Component:
    """Status banner for displaying messages."""
    
    def message_icon() -> rx.Component:
        """Icon based on message type."""
        return rx.cond(
            CameraState.message_type == "success",
            rx.icon("check", color=colors["success"]),
            rx.cond(
                CameraState.message_type == "error",
                rx.icon("x", color=colors["error"]),
                rx.cond(
                    CameraState.message_type == "warning",
                    rx.icon("triangle-alert", color=colors["warning"]),
                    rx.icon("info", color=colors["info"]),
                )
            )
        )
    
    def banner_style() -> dict:
        """Get banner style based on message type."""
        return rx.cond(
            CameraState.message_type == "success",
            {
                "background": colors["success"] + "10",
                "border": f"1px solid {colors['success']}30",
                "color": colors["success"],
            },
            rx.cond(
                CameraState.message_type == "error",
                {
                    "background": colors["error"] + "10",
                    "border": f"1px solid {colors['error']}30",
                    "color": colors["error"],
                },
                rx.cond(
                    CameraState.message_type == "warning",
                    {
                        "background": colors["warning"] + "10", 
                        "border": f"1px solid {colors['warning']}30",
                        "color": colors["warning"],
                    },
                    {
                        "background": colors["info"] + "10",
                        "border": f"1px solid {colors['info']}30",
                        "color": colors["info"],
                    },
                )
            )
        )
    
    return rx.cond(
        CameraState.message != "",
        rx.box(
            rx.hstack(
                message_icon(),
                rx.text(
                    CameraState.message,
                    font_weight="500",
                ),
                rx.spacer(),
                rx.button(
                    rx.icon("x", size=16),
                    variant="ghost",
                    size="1",
                    on_click=CameraState.clear_message,
                ),
                spacing=spacing["md"],
                align="center",
                width="100%",
            ),
            **banner_style(),
            border_radius=radius["md"],
            padding=spacing["md"],
            margin_bottom=spacing["lg"],
        ),
    )