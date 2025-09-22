"""Camera grid layout component."""

import reflex as rx
from ..state.camera_state import CameraState
from ..styles.theme import colors, spacing, css_spacing, radius, shadows, layout
from .camera_card import camera_card

def camera_grid() -> rx.Component:
    """Grid layout for displaying camera cards."""
    
    def empty_state() -> rx.Component:
        """Modern empty state using rx.center for proper centering."""
        return rx.center(
            rx.flex(
                rx.center(
                    rx.icon("camera-off", size=48, color=colors["gray_400"]),
                    background="linear-gradient(135deg, #f1f5f9, #e2e8f0)",
                    border_radius="50%",
                    padding=css_spacing["lg"],
                    box_shadow=shadows["sm"],
                ),
                rx.heading(
                    "No Cameras Found",
                    size="6",
                    font_weight="700",
                    color=colors["gray_800"],
                    text_align="center",
                ),
                rx.text(
                    "Check your camera connections and API status",
                    color=colors["gray_600"],
                    text_align="center",
                    font_size="1.125rem",
                    max_width="400px",
                    line_height="1.6",
                ),
                rx.flex(
                    rx.button(
                        rx.icon("refresh-ccw", size=16),
                        " Refresh Cameras",
                        size="3",
                        variant="solid",
                        color_scheme="blue",
                        on_click=CameraState.refresh_cameras,
                    ),
                    rx.text(
                        "or check your camera API connection",
                        font_size="0.875rem",
                        color=colors["gray_500"],
                        text_align="center",
                    ),
                    direction="column",
                    gap=spacing["md"],
                    align="center",
                ),
                direction="column",
                gap=spacing["lg"],
                align="center",
                justify="center",
                max_width="500px",
                background="linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)",
                border=f"2px dashed {colors['border']}",
                border_radius=radius["xl"],
                padding=css_spacing["xl"],
            ),
            min_height="350px",
            width="100%",
        )
    
    def loading_state() -> rx.Component:
        """Modern loading state using rx.center for proper centering."""
        return rx.center(
            rx.flex(
                rx.center(
                    rx.spinner(size="3", color=colors["primary"]),
                    background="linear-gradient(135deg, #eff6ff, #dbeafe)",
                    border_radius="50%",
                    padding=css_spacing["lg"],
                    box_shadow=shadows["sm"],
                ),
                rx.heading(
                    "Loading Cameras...",
                    size="5",
                    font_weight="600",
                    color=colors["gray_800"],
                    text_align="center",
                ),
                rx.text(
                    "Discovering available camera hardware",
                    color=colors["gray_600"],
                    text_align="center",
                    font_size="1rem",
                ),
                direction="column",
                gap=spacing["lg"],
                align="center",
                justify="center",
                max_width="400px",
                background="linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)",
                border=f"1px solid {colors['border']}",
                border_radius=radius["xl"],
                padding=css_spacing["xl"],
                box_shadow=shadows["sm"],
            ),
            min_height="300px",
            width="100%",
        )
    
    def grid_content() -> rx.Component:
        """Main grid content with properly centered camera cards."""
        return rx.center(
            rx.box(
                rx.foreach(
                    CameraState.cameras,
                    lambda camera: camera_card(camera)
                ),
                display="grid",
                grid_template_columns="repeat(auto-fill, minmax(320px, 1fr))",
                gap=css_spacing["xl"],
                width="100%",
                max_width="1200px",
                justify_items="center",
                align_items="start",
                padding=css_spacing["md"],
            ),
            width="100%",
        )
    
    return rx.cond(
        CameraState.is_loading,
        loading_state(),
        rx.cond(
            CameraState.has_cameras,
            grid_content(),
            empty_state(),
        )
    )

def camera_grid_header() -> rx.Component:
    """Modern header section using Reflex flex components."""
    return rx.box(
        rx.flex(
            # Left side - title and icon
            rx.flex(
                rx.center(
                    rx.icon("camera", size=28),
                    background="linear-gradient(135deg, #3b82f6, #1e40af)",
                    color=colors["white"],
                    border_radius=radius["lg"],
                    padding=css_spacing["md"],
                    box_shadow=shadows["md"],
                ),
                rx.flex(
                    rx.heading(
                        "Camera Configurator",
                        size="8",
                        color=colors["gray_900"],
                        font_weight="700",
                    ),
                    rx.text(
                        "Manage and configure your camera hardware",
                        color=colors["gray_600"],
                        font_size="1.125rem",
                        font_weight="500",
                    ),
                    direction="column",
                    gap="1",
                    align="start",
                ),
                gap=layout["content_gap"],
                align="center",
            ),
            # Right side - stats badges
            rx.flex(
                rx.center(
                    rx.flex(
                        rx.text(
                            CameraState.camera_count,
                            font_size="1.5rem",
                            font_weight="700",
                            color=colors["primary"],
                            line_height="1",
                        ),
                        rx.text(
                            "Total Cameras",
                            font_size="0.75rem",
                            color=colors["gray_500"],
                            font_weight="500",
                        ),
                        direction="column",
                        gap="1",
                        align="center",
                    ),
                    background=colors["primary"] + "10",
                    border=f"1px solid {colors['primary']}30",
                    border_radius=radius["lg"],
                    padding=css_spacing["md"],
                    min_width="100px",
                ),
                rx.center(
                    rx.flex(
                        rx.text(
                            CameraState.initialized_camera_count,
                            font_size="1.5rem",
                            font_weight="700",
                            color=colors["success"],
                            line_height="1",
                        ),
                        rx.text(
                            "Initialized",
                            font_size="0.75rem",
                            color=colors["gray_500"],
                            font_weight="500",
                        ),
                        direction="column",
                        gap="1",
                        align="center",
                    ),
                    background=colors["success"] + "10",
                    border=f"1px solid {colors['success']}30",
                    border_radius=radius["lg"],
                    padding=css_spacing["md"],
                    min_width="100px",
                ),
                gap=layout["content_gap"],
                align="center",
            ),
            justify="between",
            align="center",
            width="100%",
        ),
        background="linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)",
        border=f"1px solid {colors['border']}",
        border_radius=radius["lg"],
        box_shadow=shadows["sm"],
        padding=css_spacing["lg"],
        margin_bottom=css_spacing["lg"],
    )

def camera_grid_controls() -> rx.Component:
    """Modern control panel using Reflex flex components."""
    return rx.box(
        rx.flex(
            # Left side - API status
            rx.cond(
                ~CameraState.api_connected,
                rx.center(
                    rx.flex(
                        rx.icon("wifi-off", size=16, color=colors["error"]),
                        rx.text(
                            "API Disconnected",
                            font_weight="600",
                            color=colors["error"],
                        ),
                        gap=spacing["sm"],
                        align="center",
                    ),
                    background=colors["error"] + "15",
                    border=f"1px solid {colors['error']}40",
                    border_radius=radius["lg"],
                    padding=f"{css_spacing['sm']} {css_spacing['md']}",
                ),
                rx.center(
                    rx.flex(
                        rx.icon("wifi", size=16, color=colors["success"]),
                        rx.text(
                            "API Connected",
                            font_weight="600",
                            color=colors["success"],
                        ),
                        gap=spacing["sm"],
                        align="center",
                    ),
                    background=colors["success"] + "15",
                    border=f"1px solid {colors['success']}40",
                    border_radius=radius["lg"],
                    padding=f"{css_spacing['sm']} {css_spacing['md']}",
                ),
            ),
            # Right side - Action buttons
            rx.flex(
                rx.button(
                    rx.icon("refresh-ccw", size=16),
                    " Refresh Cameras",
                    size="3",
                    variant="outline",
                    on_click=CameraState.refresh_cameras,
                    disabled=CameraState.is_loading,
                    color_scheme="blue",
                ),
                rx.button(
                    rx.icon("power", size=16),
                    " Close All",
                    size="3",
                    variant="outline",
                    color_scheme="red",
                    on_click=CameraState.close_all_cameras,
                    disabled=rx.cond(
                        CameraState.initialized_camera_count == 0,
                        True,
                        CameraState.is_loading,
                    ),
                ),
                gap=layout["content_gap"],
                align="center",
            ),
            justify="between",
            align="center",
            width="100%",
        ),
        background=colors["white"],
        border=f"1px solid {colors['border']}",
        border_radius=radius["lg"],
        box_shadow=shadows["sm"],
        padding=css_spacing["lg"],
        margin_bottom=css_spacing["lg"],
    )