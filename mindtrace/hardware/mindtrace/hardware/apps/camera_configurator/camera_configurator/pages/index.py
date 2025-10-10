"""Main index page for camera configurator."""

import reflex as rx

from ..components.camera_grid import camera_grid, camera_grid_controls, camera_grid_header
from ..components.camera_modal import camera_modal
from ..components.layout import main_layout, page_container
from ..components.status_banner import status_banner
from ..state.camera_state import CameraState
from ..styles.theme import colors, css_spacing, layout, spacing


def index_page() -> rx.Component:
    """Main camera configurator page."""

    def page_content() -> rx.Component:
        """Main page content using proper layout approach."""
        return rx.box(
            camera_grid_header(),
            status_banner(),
            camera_grid_controls(),
            camera_grid(),
            display="flex",
            flex_direction="column",
            gap=layout["content_gap"],
            width="100%",
        )

    def captured_image_viewer() -> rx.Component:
        """Display captured image if available."""
        return rx.cond(
            CameraState.captured_image is not None,
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.text(
                            "Captured Image",
                            font_weight="600",
                            font_size="1.125rem",
                            color=colors["gray_900"],
                        ),
                        rx.spacer(),
                        rx.button(
                            rx.icon("x"),
                            variant="ghost",
                            size="2",
                            on_click=lambda: CameraState.set_captured_image(None),
                        ),
                        width="100%",
                        align="center",
                    ),
                    rx.image(
                        src=f"data:image/png;base64,{CameraState.captured_image}",
                        max_width="100%",
                        max_height="400px",
                        border_radius=css_spacing["md"],
                        border=f"1px solid {colors['border']}",
                    ),
                    spacing=spacing["md"],
                    width="100%",
                ),
                background=colors["white"],
                border=f"1px solid {colors['border']}",
                border_radius=css_spacing["lg"],
                padding=css_spacing["lg"],
                margin_top=css_spacing["lg"],
            ),
        )

    def active_streams_summary() -> rx.Component:
        """Removed - streams are displayed in camera cards."""
        return rx.fragment()

    return rx.box(
        main_layout(
            page_container(
                rx.vstack(
                    page_content(),
                    captured_image_viewer(),
                    active_streams_summary(),
                    camera_modal(),
                    spacing=spacing["lg"],
                    width="100%",
                )
            )
        ),
        on_mount=CameraState.refresh_cameras,
    )
