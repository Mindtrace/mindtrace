import reflex as rx
from poseidon.components.image_components import (
    COLORS, TYPOGRAPHY, SIZING, SPACING, content_variants, button_variants, card_variants
)
from poseidon.state.model_deployment import ModelDeploymentState, CameraDict

def camera_selection_card(camera: rx.Var[CameraDict]) -> rx.Component:
    """Individual camera selection card - compact version"""
    return rx.card(
        rx.hstack(
            # Selection indicator
            rx.box(
                rx.cond(
                    ModelDeploymentState.selected_camera_ids.contains(camera.id),
                    rx.text("✓", color="green", font_weight="600", font_size="0.875rem"),
                    rx.text("○", color=COLORS["text_muted"], font_size="0.875rem"),
                ),
                width="1.25rem",
                height="1.25rem",
                display="flex",
                align_items="center",
                justify_content="center",
                border_radius="50%",
                border=f"1px solid {COLORS['border']}",
                background=rx.cond(
                    ModelDeploymentState.selected_camera_ids.contains(camera.id),
                    "rgba(0, 255, 0, 0.1)",
                    "transparent"
                ),
                cursor="pointer",
            ),
            
            # Camera info
            rx.vstack(
                rx.text(
                    camera.name,
                    font_weight="600",
                    font_size="0.875rem",
                    color=COLORS["primary"],
                ),
                rx.text(
                    f"{camera.backend} • {camera.device_name}",
                    font_size="0.75rem",
                    color=COLORS["text_muted"],
                ),
                spacing="1",
                align="start",
                flex="1",
            ),
            
            # Status and location
            rx.vstack(
                rx.badge(
                    camera.status,
                    color_scheme=rx.cond(
                        camera.status == "active",
                        "green",
                        rx.cond(
                            camera.status == "inactive",
                            "gray",
                            "red"
                        )
                    ),
                    size="1",
                ),
                rx.cond(
                    camera.location != "",
                    rx.text(
                        camera.location,
                        font_size="0.75rem",
                        color=COLORS["text_muted"],
                    ),
                    rx.fragment(),
                ),
                spacing="1",
                align="end",
            ),
            
            spacing="3",
            align="center",
            width="100%",
        ),
        
        # Card styling
        **{**card_variants["base"],"padding": SPACING["sm"]},
       
        min_height="60px",
        width="100%",
        _hover={
            "box_shadow": "0 2px 8px rgba(0, 0, 0, 0.1)",
            "transform": "translateY(-1px)",
        },
        transition="all 0.2s ease",
        cursor="pointer",
        on_click=ModelDeploymentState.toggle_camera_selection(camera.id),
    )

def camera_selection_grid() -> rx.Component:
    """List of camera selection cards"""
    return rx.box(
        rx.vstack(
            # Header with selection info
            rx.hstack(
                rx.text(
                    "Select Cameras",
                    font_size="1.25rem",
                    font_weight="600",
                    color=COLORS["primary"],
                ),
                rx.spacer(),
                rx.text(
                    f"{ModelDeploymentState.selected_cameras_count} cameras selected",
                    font_size="0.875rem",
                    color=COLORS["text_muted"],
                ),
                width="100%",
                align="center",
            ),
            
            # Action buttons
            rx.hstack(
                rx.button(
                    "Select All",
                    on_click=ModelDeploymentState.select_all_cameras,
                    **button_variants["secondary"],
                    size="2",
                ),
                rx.button(
                    "Clear Selection",
                    on_click=ModelDeploymentState.clear_selections,
                    **button_variants["secondary"],
                    size="2",
                ),
                spacing="2",
            ),
            
            # Camera list
            rx.cond(
                ModelDeploymentState.available_cameras.length() > 0,
                rx.vstack(
                    rx.foreach(
                        ModelDeploymentState.available_cameras,
                        camera_selection_card,
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.center(
                    rx.vstack(
                        rx.box(
                            "📷",
                            font_size="3rem",
                            color=COLORS["text_muted"],
                        ),
                        rx.text(
                            "No cameras available",
                            font_size="1.125rem",
                            font_weight="500",
                            color=COLORS["secondary"],
                        ),
                        rx.text(
                            "Make sure cameras are assigned to your project and initialized in the Camera Configurator",
                            font_size="0.875rem",
                            color=COLORS["text_muted"],
                            text_align="center",
                        ),
                        spacing="3",
                        align="center",
                    ),
                    padding=SPACING["xl"],
                    width="100%",
                ),
            ),
            
            spacing="4",
            width="100%",
        ),
        width="100%",
    )