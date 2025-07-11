import reflex as rx
from poseidon.components import sidebar, app_header, page_container, card_grid, content_section
from poseidon.components.cards import profile_info_card
from poseidon.components.image_components import card_variants, COLORS, TYPOGRAPHY, SIZING, SPACING
from poseidon.state.camera import CameraState
from poseidon.components.camera_config_modal import camera_config_modal
from poseidon.components.camera_card import camera_card
from poseidon.components.camera_diagnostics import camera_diagnostics
from poseidon.components.image_display import image_display
from poseidon.components.status_banner import status_banner


def modern_card(content: rx.Component, title: str = "", icon: str = "") -> rx.Component:
    """Clean, professional card component with minimal styling"""
    return rx.box(
        rx.vstack(
            rx.cond(
                title != "",
                rx.hstack(
                    rx.cond(
                        icon != "",
                        rx.text(icon, font_size="1.25rem", color="#374151"),
                        rx.box()
                    ),
                    rx.text(
                        title,
                        font_size="1.125rem",
                        font_weight="600",
                        color="#111827",
                    ),
                    spacing="2",
                    align="center",
                    margin_bottom="1rem",
                    ),
                rx.box()
            ),
            content,
            spacing="0",
            width="100%",
            align="stretch",
        ),
        background="white",
        border="1px solid #E5E7EB",
        border_radius="8px",
        padding="1.5rem",
        box_shadow="0 1px 3px rgba(0, 0, 0, 0.1)",
        width="100%",
    )


def camera_grid() -> rx.Component:
    """Modern camera grid with modular camera cards"""
    return rx.cond(
        CameraState.cameras.length() > 0,
        rx.grid(
            rx.foreach(
                CameraState.cameras,
                lambda cam: camera_card(cam),
            ),
            columns="repeat(auto-fill, minmax(320px, 1fr))",
            gap="6",
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


def camera_configurator_page() -> rx.Component:
    """
    Clean, professional Camera Configurator page with modal popup configuration.
    """
    return rx.box(
        # Sidebar navigation (fixed)
        rx.box(
            sidebar(),
            position="fixed",
            left="0",
            top="0",
            width="240px",
            height="100vh",
            z_index="1000",
        ),
        # Header (fixed)
        rx.box(
            app_header(),
            position="fixed",
            top="0",
            left="240px",
            right="0",
            height="60px",
            z_index="999",
        ),
        # Main content
        rx.box(
            rx.container(
                rx.vstack(
                    # Page header
                    rx.vstack(
                        rx.hstack(
                            rx.box(
                                "📷",
                                font_size="2.5rem",
                                color="#111827",
                                padding="1rem",
                                background="#F9FAFB",
                                border_radius="12px",
                                border="1px solid #E5E7EB",
                                box_shadow="0 2px 4px rgba(0, 0, 0, 0.05)",
                            ),
                            rx.vstack(
                                rx.heading(
                                    "Camera Configurator",
                                    font_size="2rem",
                                    font_weight="700",
                                    color="#111827",
                                    margin="0",
                                ),
                                rx.text(
                                    "Manage and configure all connected cameras",
                                    color="#6B7280",
                                    font_size="1rem",
                                    margin="0",
                                ),
                                spacing="2",
                                align="start",
                            ),
                            rx.spacer(),
                            # Refresh button
                            rx.button(
                                rx.hstack(
                                    rx.text("🔄", font_size="1rem"),
                                    rx.text("Refresh", font_weight="500"),
                                    spacing="2",
                                    align="center",
                                ),
                                on_click=CameraState.fetch_camera_list,
                                variant="outline",
                                color_scheme="gray",
                                size="2",
                                _hover={"background": "#F9FAFB"},
                                transition="all 0.2s ease",
                            ),
                            spacing="4",
                            align="center",
                            width="100%",
                        ),
                        spacing="4",
                        width="100%",
                        margin_bottom="2rem",
                    ),
                    
                    # Status messages
                    status_banner(),
                    
                    # Loading state
                    rx.cond(
                        CameraState.is_loading,
                        rx.center(
                            rx.vstack(
                                rx.spinner(size="3", color="#111827"),
                                rx.text("Loading cameras...", color="#6B7280", font_weight="500"),
                                spacing="3",
                                align="center",
                            ),
                            padding="3rem",
                        ),
                        # Main content
                        rx.vstack(
                            # Camera grid section
                            modern_card(
                                camera_grid(),
                                title="Available Cameras",
                                icon="📹"
                            ),
                            
                            # Two-column layout for diagnostics and image display
                            rx.grid(
                                modern_card(
                                    camera_diagnostics(),
                                    title="",
                                    icon=""
                                ),
                                modern_card(
                                    image_display(),
                                    title="",
                                    icon=""
                                ),
                                columns="2",
                                gap="6",
                                width="100%",
                            ),
                            
                            spacing="6",
                            width="100%",
                        ),
                    ),
                    spacing="0",
                    width="100%",
                    align="stretch",
                ),
                max_width="1400px",
                padding_x="2rem",
                padding_y="2rem",
            ),
            margin_left="240px",
            margin_top="60px",
            min_height="calc(100vh - 60px)",
            background="#F9FAFB",
            width="calc(100% - 240px)",
        ),
        # Camera configuration popup
        # The camera_configuration_popup function is now embedded in camera_grid()
        width="100%",
        min_height="100vh",
        on_mount=CameraState.fetch_camera_list,
    ) 