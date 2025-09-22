"""Camera card component for displaying camera information and controls."""

import reflex as rx
from ..state.camera_state import CameraState
from ..styles.theme import colors, spacing, css_spacing, radius, shadows, status_badges

def camera_card(camera_name: str) -> rx.Component:
    """Camera card component with status and controls."""
    
    def stream_display() -> rx.Component:
        """Video stream display component - only shows when this specific camera is streaming."""
        # Use direct state comparison instead of method calls for better reactivity
        return rx.cond(
            CameraState.streaming_camera_name == camera_name,
            # Show stream when this specific camera is streaming
            rx.box(
                # Removed red LIVE indicator
                rx.image(
                    src=CameraState.streaming_url,
                    alt=f"Live stream from {camera_name}",
                    width="100%",
                    height="200px",
                    object_fit="cover",
                    border_radius=radius["lg"],
                    border=f"2px solid {colors['primary']}",
                    style={
                        "image-rendering": "auto",
                        "image-orientation": "from-image",
                    },
                ),
                width="100%",
                margin_bottom=spacing["md"],
                background_color="rgba(255, 0, 0, 0.1)",
                padding="8px",
                border_radius=radius["lg"],
            ),
            # Completely empty when not streaming - no box, no content
            rx.fragment(),
        )
    
    def camera_icon() -> rx.Component:
        """Camera icon with dynamic status indication."""
        return rx.box(
            rx.cond(
                CameraState.camera_statuses.get(camera_name, "unknown") == "initialized",
                rx.icon("video", size=24, color=colors["success"]),
                rx.cond(
                    CameraState.camera_statuses.get(camera_name, "unknown") == "available", 
                    rx.icon("camera", size=24, color=colors["warning"]),
                    rx.cond(
                        CameraState.camera_statuses.get(camera_name, "unknown") == "error",
                        rx.icon("camera-off", size=24, color=colors["error"]),
                        rx.icon("circle-help", size=24, color=colors["gray_400"]),
                    )
                )
            ),
            width="60px",
            height="60px",
            display="flex",
            align_items="center",
            justify_content="center",
            background=rx.cond(
                CameraState.camera_statuses.get(camera_name, "unknown") == "initialized",
                colors["success"] + "15",
                rx.cond(
                    CameraState.camera_statuses.get(camera_name, "unknown") == "available",
                    colors["warning"] + "15",
                    rx.cond(
                        CameraState.camera_statuses.get(camera_name, "unknown") == "error",
                        colors["error"] + "15",
                        colors["gray_50"],
                    )
                )
            ),
            border_radius=radius["lg"],
            border=rx.cond(
                CameraState.camera_statuses.get(camera_name, "unknown") == "initialized",
                f"2px solid {colors['success']}50",
                rx.cond(
                    CameraState.camera_statuses.get(camera_name, "unknown") == "available",
                    f"2px solid {colors['warning']}50", 
                    rx.cond(
                        CameraState.camera_statuses.get(camera_name, "unknown") == "error",
                        f"2px solid {colors['error']}50",
                        f"1px solid {colors['border']}",
                    )
                )
            ),
        )
    
    def camera_header() -> rx.Component:
        """Camera header with name and status."""
        return rx.hstack(
            camera_icon(),
            rx.vstack(
                rx.text(
                    camera_name,
                    font_weight="600",
                    font_size="1.1rem",
                    color=colors["gray_900"],
                ),
                rx.text(
                    f"ID: {camera_name}",
                    font_size="0.875rem",
                    color=colors["gray_500"],
                ),
                status_badge(camera_name),
                spacing=spacing["xs"],
                align="start",
                width="100%",
            ),
            spacing=spacing["md"],
            align="center",
            width="100%",
        )
    
    def status_badge(camera_name: str) -> rx.Component:
        """Modern status badge for camera with enhanced styling."""
        return rx.cond(
            CameraState.camera_statuses.get(camera_name, "unknown") == "initialized",
            rx.box(
                rx.hstack(
                    rx.box(
                        width="8px",
                        height="8px",
                        border_radius="50%",
                        background=colors["success"],
                        box_shadow=f"0 0 0 2px {colors['success']}40",
                    ),
                    rx.text(
                        "Ready",
                        font_weight="600",
                        font_size="0.75rem",
                        color=colors["success"],
                    ),
                    spacing=spacing["sm"],
                    align="center",
                ),
                background=colors["success"] + "15",
                border=f"1px solid {colors['success']}40",
                border_radius=radius["full"],
                padding=f"{css_spacing['xs']} {css_spacing['sm']}",
            ),
            rx.cond(
                CameraState.camera_statuses.get(camera_name, "unknown") == "available",
                rx.box(
                    rx.hstack(
                        rx.box(
                            width="8px",
                            height="8px",
                            border_radius="50%",
                            background=colors["warning"],
                            box_shadow=f"0 0 0 2px {colors['warning']}40",
                        ),
                        rx.text(
                            "Available",
                            font_weight="600",
                            font_size="0.75rem",
                            color=colors["warning"],
                        ),
                        spacing=spacing["sm"],
                        align="center",
                    ),
                    background=colors["warning"] + "15",
                    border=f"1px solid {colors['warning']}40",
                    border_radius=radius["full"],
                    padding=f"{css_spacing['xs']} {css_spacing['sm']}",
                ),
                rx.cond(
                    CameraState.camera_statuses.get(camera_name, "unknown") == "busy",
                    rx.box(
                        rx.hstack(
                            rx.box(
                                width="8px",
                                height="8px",
                                border_radius="50%",
                                background=colors["info"],
                                box_shadow=f"0 0 0 2px {colors['info']}40",
                            ),
                            rx.text(
                                "Busy",
                                font_weight="600",
                                font_size="0.75rem",
                                color=colors["info"],
                            ),
                            spacing=spacing["sm"],
                            align="center",
                        ),
                        background=colors["info"] + "15",
                        border=f"1px solid {colors['info']}40",
                        border_radius=radius["full"],
                        padding=f"{css_spacing['xs']} {css_spacing['sm']}",
                    ),
                    rx.cond(
                        CameraState.camera_statuses.get(camera_name, "unknown") == "error",
                        rx.box(
                            rx.hstack(
                                rx.box(
                                    width="8px",
                                    height="8px",
                                    border_radius="50%",
                                    background=colors["error"],
                                    box_shadow=f"0 0 0 2px {colors['error']}40",
                                ),
                                rx.text(
                                    "Error",
                                    font_weight="600",
                                    font_size="0.75rem",
                                    color=colors["error"],
                                ),
                                spacing=spacing["sm"],
                                align="center",
                            ),
                            background=colors["error"] + "15",
                            border=f"1px solid {colors['error']}40",
                            border_radius=radius["full"],
                            padding=f"{css_spacing['xs']} {css_spacing['sm']}",
                        ),
                        rx.box(
                            rx.hstack(
                                rx.box(
                                    width="8px",
                                    height="8px",
                                    border_radius="50%",
                                    background=colors["gray_400"],
                                ),
                                rx.text(
                                    "Unknown",
                                    font_weight="600",
                                    font_size="0.75rem",
                                    color=colors["gray_500"],
                                ),
                                spacing=spacing["sm"],
                                align="center",
                            ),
                            background=colors["gray_50"],
                            border=f"1px solid {colors['border']}",
                            border_radius=radius["full"],
                            padding=f"{css_spacing['xs']} {css_spacing['sm']}",
                        ),
                    )
                )
            )
        )
    
    def action_buttons(camera_name: str) -> rx.Component:
        """Action buttons for camera operations."""
        return rx.vstack(
            # Initialize/Deinitialize button
            rx.cond(
                CameraState.camera_statuses.get(camera_name, "unknown") == "initialized",
                rx.button(
                    "Deinitialize",
                    size="2",
                    variant="solid",
                    color_scheme="red",
                    width="100%",
                    on_click=CameraState.close_camera(camera_name),
                ),
                rx.button(
                    "Initialize",
                    size="2", 
                    variant="solid",
                    color_scheme="blue",
                    width="100%",
                    on_click=CameraState.initialize_camera(camera_name),
                ),
            ),
            
            # Configuration button (only for initialized cameras)
            rx.cond(
                CameraState.camera_statuses.get(camera_name, "unknown") == "initialized",
                rx.button(
                    rx.icon("settings"),
                    " Configure",
                    size="2",
                    variant="outline",
                    width="100%",
                    on_click=CameraState.open_config_modal(camera_name),
                ),
            ),
            
            # Capture button (only for initialized cameras)
            rx.cond(
                CameraState.camera_statuses.get(camera_name, "unknown") == "initialized",
                rx.button(
                    rx.cond(
                        CameraState.capture_loading,
                        rx.spinner(size="1"),
                        rx.icon("camera"),
                    ),
                    " Capture",
                    size="2",
                    variant="outline",
                    width="100%",
                    disabled=CameraState.capture_loading,
                    on_click=CameraState.capture_image(camera_name),
                ),
            ),
            
            # Stream button (only for initialized cameras)
            rx.cond(
                CameraState.camera_statuses.get(camera_name, "unknown") == "initialized",
                rx.cond(
                    CameraState.streaming_camera_name == camera_name,
                    rx.button(
                        rx.icon("square"),
                        " Stop Stream",
                        size="2",
                        variant="outline",
                        color_scheme="red",
                        width="100%",
                        on_click=CameraState.stop_stream(camera_name),
                    ),
                    rx.button(
                        rx.icon("play"),
                        " Start Stream",
                        size="2",
                        variant="outline",
                        color_scheme="green",
                        width="100%",
                        on_click=CameraState.start_stream(camera_name),
                    ),
                ),
            ),
            
            spacing=spacing["sm"],
            width="100%",
        )
    
    def camera_info(camera_name: str) -> rx.Component:
        """Camera configuration information."""
        return rx.cond(
            CameraState.camera_configs.get(camera_name, {}) != {},
            rx.vstack(
                rx.text(
                    "Configuration:",
                    font_weight="500",
                    font_size="0.875rem",
                    color=colors["gray_700"],
                ),
                rx.vstack(
                    rx.text(
                        f"Exposure: {CameraState.camera_configs.get(camera_name, {}).get('exposure', 'N/A')}",
                        font_size="0.75rem",
                        color=colors["gray_600"],
                    ),
                    rx.text(
                        f"Gain: {CameraState.camera_configs.get(camera_name, {}).get('gain', 'N/A')}",
                        font_size="0.75rem",
                        color=colors["gray_600"],
                    ),
                    rx.text(
                        f"Mode: {CameraState.camera_configs.get(camera_name, {}).get('trigger_mode', 'N/A')}",
                        font_size="0.75rem",
                        color=colors["gray_600"],
                    ),
                    spacing=spacing["xs"],
                    align="start",
                ),
                spacing=spacing["xs"],
                align="start",
                width="100%",
                padding_top=spacing["sm"],
                border_top=f"1px solid {colors['border_light']}",
            ),
        )
    
    return rx.flex(
        camera_header(),
        stream_display(),
        action_buttons(camera_name),
        camera_info(camera_name),
        direction="column",
        gap=spacing["lg"],
        background="linear-gradient(135deg, #ffffff 0%, #fefefe 100%)",
        border=f"1px solid {colors['border']}",
        border_radius=radius["xl"],
        box_shadow="0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)",
        padding=css_spacing["lg"],
        transition="all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        _hover={
            "box_shadow": "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
            "transform": "translateY(-4px)",
            "border_color": colors["primary"],
            "background": "linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)",
        },
        width="100%",
        max_width="400px",
        min_height="fit-content",
    )