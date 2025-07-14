import reflex as rx
from poseidon.components import sidebar, app_header, page_container, content_section
from poseidon.components.image_components import (
    COLORS, TYPOGRAPHY, SIZING, SPACING, content_variants, button_variants, card_variants
)
from poseidon.state.camera import CameraState
from poseidon.components.camera_config_modal import camera_config_modal
from poseidon.components.camera_card import camera_card
from poseidon.components.status_banner import status_banner


def camera_grid() -> rx.Component:
    """Camera grid with modular camera cards"""
    return rx.cond(
        CameraState.cameras.length() > 0,
        rx.box(
            rx.foreach(
                CameraState.cameras,
                lambda cam: camera_card(cam),
            ),
            display="grid",
            grid_template_columns="repeat(auto-fill, minmax(320px, 1fr))",
            gap=SPACING["md"],
            padding=SPACING["md"],
            width="100%",
        ),
        rx.center(
            rx.vstack(
                rx.box(
                    "📷",
                    font_size="3rem",
                    color="#9CA3AF",
                    margin_bottom="1rem",
                ),
                rx.text(
                    "No cameras detected",
                    font_size="1.25rem",
                    font_weight="500",
                    color="#374151",
                ),
                rx.text(
                    "Check your camera connections and try refreshing",
                    color="#6B7280",
                    text_align="center",
                    font_size="0.875rem",
                ),
                spacing="3",
                align="center",
            ),
            padding="3rem",
        ),
    )


def camera_configurator_content() -> rx.Component:
    """Camera configurator content using unified Poseidon UI components."""
    return rx.box(
        # Sidebar navigation (fixed position)
        rx.box(
            sidebar(),
            position="fixed",
            left="0",
            top="0",
            width="240px",
            height="100vh",
            z_index="1000",
        ),
        
        # Header (fixed position)
        rx.box(
            app_header(),
            position="fixed",
            top="0",
            left="240px",
            right="0",
            height="60px",
            z_index="999",
        ),
        
        # Main content using page_container
        page_container(
            # Page header
            rx.box(
                rx.heading("Camera Configurator", **content_variants["page_title"]),
                rx.text("Manage and configure all connected cameras", **content_variants["page_subtitle"]),
                **content_variants["page_header"]
            ),
            
            # Action buttons
            rx.hstack(
                rx.button(
                    rx.hstack(
                        rx.text("🔄", font_size="1rem"),
                        rx.text("Refresh", font_weight="500"),
                        spacing="2",
                        align="center",
                    ),
                    on_click=CameraState.fetch_camera_list,
                    **button_variants["secondary"],
                ),
                rx.button(
                    rx.hstack(
                        rx.text("❌", font_size="1rem"),
                        rx.text("Close All Cameras", font_weight="500"),
                        spacing="2",
                        align="center",
                    ),
                    on_click=CameraState.close_all_cameras,
                    variant="solid",
                    color_scheme="red",
                    size="2",
                    _hover={"transform": "translateY(-1px)", "box_shadow": "0 4px 8px rgba(0, 0, 0, 0.15)"},
                    transition="all 0.2s ease",
                ),
                rx.spacer(),
                spacing="2",
                align="center",
                width="100%",
            ),
            
            # Status messages
            status_banner(),
            
            # Camera grid
            rx.cond(
                CameraState.is_loading,
                rx.box(
                    rx.spinner(size="3"),
                    rx.text("Loading cameras...", margin_left=SPACING["sm"], color=COLORS["text_muted"]),
                    display="flex",
                    align_items="center",
                    justify_content="center",
                    padding=SPACING["xl"],
                ),
                camera_grid(),
            ),
            
            margin_top="60px",  # Account for header
        ),
        
        # Camera configuration modal
        camera_config_modal(),
        
        width="100%",
        min_height="100vh",
        position="relative",
        
        # Load cameras on mount
        on_mount=CameraState.fetch_camera_list,
    )


def camera_configurator_page() -> rx.Component:
    """Camera Configurator page with clean, focused layout."""
    return camera_configurator_content() 