import reflex as rx
from poseidon.components import sidebar, app_header, page_container, content_section
from poseidon.components.image_components import (
    COLORS, TYPOGRAPHY, SIZING, SPACING, content_variants, button_variants, card_variants
)
from poseidon.state.camera import CameraState
from poseidon.state.auth import AuthState
from poseidon.components.camera_config_modal import camera_config_modal
from poseidon.components.camera_card import camera_card
from poseidon.components.status_banner import status_banner
from poseidon.components.popups import camera_assignment_popup


def project_selector() -> rx.Component:
    """Project selector dropdown for scoped camera access."""
    return rx.vstack(
        rx.text(
            rx.cond(
                CameraState.is_super_admin,
                "Select Project (Optional for Super Admin)",
                "Select Project"
            ),
            font_size="1rem",
            font_weight="600",
            color="#374151",
            margin_bottom="0.5rem",
        ),
        rx.cond(
            CameraState.available_projects.length() > 0,
            rx.select(
                CameraState.project_names,
                placeholder="Choose a project...",
                value=CameraState.selected_project_name,
                on_change=lambda project_name: CameraState.select_project_by_name(project_name),
                size="3",
                width="100%",
            ),
            rx.box(
                rx.text(
                    "No projects available",
                    color="#6B7280",
                    font_size="0.875rem",
                ),
                padding="0.75rem",
                background="#F9FAFB",
                border_radius="8px",
                border="1px solid #E5E7EB",
                width="100%",
            ),
        ),
        rx.cond(
            CameraState.selected_project_name != "",
            rx.text(
                f"Selected: {CameraState.selected_project_name}",
                font_size="0.875rem",
                color="#059669",
                font_weight="500",
                margin_top="0.5rem",
            ),
        ),

        width="100%",
        spacing="2",
    )


def camera_grid() -> rx.Component:
    """Camera grid with modular camera cards"""
    return rx.cond(
        (CameraState.project_id != "") | CameraState.is_super_admin,
        rx.cond(
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
                        "No cameras assigned to this project",
                        font_size="1.25rem",
                        font_weight="500",
                        color="#374151",
                    ),
                    rx.text(
                        "Contact your administrator to assign cameras to this project",
                        color="#6B7280",
                        text_align="center",
                        font_size="0.875rem",
                    ),
                    spacing="3",
                    align="center",
                ),
                padding="3rem",
            ),
        ),
        rx.center(
            rx.vstack(
                rx.box(
                    "🎯",
                    font_size="3rem",
                    color="#9CA3AF",
                    margin_bottom="1rem",
                ),
                rx.text(
                    rx.cond(
                        CameraState.is_admin | CameraState.is_super_admin,
                        "Select a project or use 'All Cameras' to view cameras",
                        "Select a project to view cameras"
                    ),
                    font_size="1.25rem",
                    font_weight="500",
                    color="#374151",
                ),
                rx.text(
                    rx.cond(
                        CameraState.is_admin | CameraState.is_super_admin,
                        "As an admin, you can view all cameras or choose a specific project",
                        "Choose a project from the dropdown above to access its cameras"
                    ),
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
                rx.text("Manage and configure cameras for your projects", **content_variants["page_subtitle"]),
                **content_variants["page_header"]
            ),
            
            # Project selector section
            rx.box(
                project_selector(),
                **card_variants["base"],
                margin_bottom=SPACING["lg"],
            ),
            
            # Action buttons
            rx.cond(
                (CameraState.project_id != "") | CameraState.is_super_admin,
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
                    rx.cond(
                        CameraState.is_admin | CameraState.is_super_admin,
                        rx.text(
                            "Admin: You can assign cameras to projects",
                            font_size="0.875rem",
                            color="#059669",
                            font_weight="500",
                        ),
                        rx.text(
                            f"User: {CameraState.cameras.length()} cameras available",
                            font_size="0.875rem",
                            color="#6B7280",
                        ),
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                ),
                rx.box(height="2rem"),  # Spacer when no project selected
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
        
        # Camera assignment popup
        camera_assignment_popup(),
        
        width="100%",
        min_height="100vh",
        position="relative",
        
        # Initialize context on mount
        on_mount=CameraState.initialize_context,
    )


def camera_configurator_page() -> rx.Component:
    """Camera Configurator page with clean, focused layout."""
    return rx.cond(
        AuthState.is_authenticated,
        camera_configurator_content(),
        rx.center(
            rx.vstack(
                rx.text(
                    "🔒",
                    font_size="4rem",
                    color="#9CA3AF",
                ),
                rx.text(
                    "Access Denied",
                    font_size="2rem",
                    font_weight="600",
                    color="#374151",
                ),
                rx.text(
                    "Please log in to access the camera configurator",
                    color="#6B7280",
                    text_align="center",
                ),
                rx.link(
                    rx.button(
                        "Go to Login",
                        color_scheme="blue",
                        size="3",
                    ),
                    href="/login",
                ),
                spacing="4",
                align="center",
            ),
            height="100vh",
        ),
    ) 