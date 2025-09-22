"""Status banner component for displaying messages."""

import reflex as rx
from ..state.camera_state import CameraState
from ..styles.theme import colors, spacing, css_spacing, radius

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
    
    return rx.cond(
        CameraState.message != "",
        rx.center(
            rx.box(
                rx.hstack(
                message_icon(),
                rx.text(
                    CameraState.message,
                    font_weight="500",
                    color=rx.cond(
                        CameraState.message_type == "success",
                        colors["success"],
                        rx.cond(
                            CameraState.message_type == "error",
                            colors["error"],
                            rx.cond(
                                CameraState.message_type == "warning",
                                colors["warning"],
                                colors["info"],
                            )
                        )
                    ),
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
            background=rx.cond(
                CameraState.message_type == "success",
                colors["success"] + "15",
                rx.cond(
                    CameraState.message_type == "error",
                    colors["error"] + "15",
                    rx.cond(
                        CameraState.message_type == "warning",
                        colors["warning"] + "15",
                        colors["info"] + "15",
                    )
                )
            ),
            border=rx.cond(
                CameraState.message_type == "success",
                f"1px solid {colors['success']}50",
                rx.cond(
                    CameraState.message_type == "error",
                    f"1px solid {colors['error']}50",
                    rx.cond(
                        CameraState.message_type == "warning",
                        f"1px solid {colors['warning']}50",
                        f"1px solid {colors['info']}50",
                    )
                )
            ),
            border_radius=radius["md"],
            padding=css_spacing["md"],
            margin_bottom=css_spacing["lg"],
            max_width="600px",
            width="fit-content",
            ),
            width="100%",
        ),
    )