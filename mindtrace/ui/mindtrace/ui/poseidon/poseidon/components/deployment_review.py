"""
Deployment review and summary component for the final step
"""
import reflex as rx
from poseidon.components.image_components import (
    COLORS, TYPOGRAPHY, SIZING, SPACING, content_variants, button_variants, card_variants
)
from poseidon.components.status_banner import status_banner
from poseidon.state.model_deployment import ModelDeploymentState
from poseidon.backend.core.config import settings

def selected_cameras_summary() -> rx.Component:
    """Summary of selected cameras"""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.text("📷", font_size="1.25rem"),
                rx.text(
                    "Selected Cameras",
                    font_size="1.125rem",
                    font_weight="600",
                    color=COLORS["primary"],
                ),
                spacing="3",
                align="center",
            ),
            
            rx.cond(
                ModelDeploymentState.selected_cameras_count > 0,
                rx.vstack(
                    rx.hstack(
                        rx.text(
                            f"{ModelDeploymentState.selected_cameras_count} cameras selected",
                            font_size="1rem",
                            font_weight="500",
                            color=COLORS["primary"],
                        ),
                        rx.spacer(),
                        rx.button(
                            "Edit",
                            on_click=ModelDeploymentState.go_to_step(1),
                            **button_variants["ghost"],
                            size="1",
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    
                    # Camera list
                    rx.box(
                        rx.foreach(
                            ModelDeploymentState.available_cameras,
                            lambda camera: rx.cond(
                                ModelDeploymentState.selected_camera_ids.contains(camera.id),
                                rx.hstack(
                                    rx.text("✓", color="green", font_weight="600"),
                                    rx.text(
                                        camera.name,
                                        font_size="0.875rem",
                                        color=COLORS["primary"],
                                    ),
                                    rx.text(
                                        f"({camera.backend} • {camera.device_name})",
                                        font_size="0.75rem",
                                        color=COLORS["text_muted"],
                                    ),
                                    spacing="2",
                                    align="center",
                                ),
                                rx.fragment(),
                            ),
                        ),
                        max_height="200px",
                        overflow_y="auto",
                        padding=SPACING["sm"],
                        border=f"1px solid {COLORS['border']}",
                        border_radius=SIZING["border_radius"],
                        background=COLORS["background"],
                    ),
                    
                    spacing="3",
                    align="start",
                    width="100%",
                ),
                rx.text(
                    "No cameras selected",
                    font_size="0.875rem",
                    color=COLORS["text_muted"],
                    font_style="italic",
                ),
            ),
            
            spacing="3",
            align="start",
            width="100%",
        ),
        **card_variants["base"],
        flex="1",
    )

def selected_model_summary() -> rx.Component:
    """Summary of selected model"""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.text("🤖", font_size="1.25rem"),
                rx.text(
                    "Selected Model",
                    font_size="1.125rem",
                    font_weight="600",
                    color=COLORS["primary"],
                ),
                spacing="3",
                align="center",
            ),
            
            rx.cond(
                ModelDeploymentState.selected_model_name != "",
                rx.vstack(
                    rx.hstack(
                        rx.text(
                            ModelDeploymentState.selected_model_name,
                            font_size="1rem",
                            font_weight="500",
                            color=COLORS["primary"],
                        ),
                        rx.spacer(),
                        rx.button(
                            "Edit",
                            on_click=ModelDeploymentState.go_to_step(2),
                            **button_variants["ghost"],
                            size="1",
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    
                    # Model details
                    rx.box(
                        rx.vstack(
                            rx.foreach(
                                ModelDeploymentState.available_models,
                                lambda model: rx.cond(
                                    ModelDeploymentState.selected_model_id == model.id,
                                    rx.vstack(
                                        rx.hstack(
                                            rx.text(
                                                "Version:",
                                                font_size="0.875rem",
                                                font_weight="500",
                                                color=COLORS["secondary"],
                                            ),
                                            rx.text(
                                                model.version,
                                                font_size="0.875rem",
                                                color=COLORS["primary"],
                                            ),
                                            spacing="2",
                                            align="center",
                                        ),
                                        rx.hstack(
                                            rx.text(
                                                "Framework:",
                                                font_size="0.875rem",
                                                font_weight="500",
                                                color=COLORS["secondary"],
                                            ),
                                            rx.text(
                                                model.framework,
                                                font_size="0.875rem",
                                                color=COLORS["primary"],
                                            ),
                                            spacing="2",
                                            align="center",
                                        ),
                                        rx.hstack(
                                            rx.text(
                                                "Status:",
                                                font_size="0.875rem",
                                                font_weight="500",
                                                color=COLORS["secondary"],
                                            ),
                                            rx.badge(
                                                model.validation_status,
                                                color_scheme=rx.cond(
                                                    model.validation_status == "validated",
                                                    "green",
                                                    "yellow"
                                                ),
                                                size="1",
                                            ),
                                            spacing="2",
                                            align="center",
                                        ),
                                        rx.cond(
                                            model.description != "",
                                            rx.text(
                                                model.description,
                                                font_size="0.875rem",
                                                color=COLORS["text_muted"],
                                                line_height="1.4",
                                            ),
                                            rx.fragment(),
                                        ),
                                        spacing="2",
                                        align="start",
                                        width="100%",
                                    ),
                                    rx.fragment(),
                                ),
                            ),
                            spacing="2",
                            align="start",
                            width="100%",
                        ),
                        padding=SPACING["sm"],
                        border=f"1px solid {COLORS['border']}",
                        border_radius=SIZING["border_radius"],
                        background=COLORS["background"],
                    ),
                    
                    spacing="3",
                    align="start",
                    width="100%",
                ),
                rx.text(
                    "No model selected",
                    font_size="0.875rem",
                    color=COLORS["text_muted"],
                    font_style="italic",
                ),
            ),
            
            spacing="3",
            align="start",
            width="100%",
        ),
        **card_variants["base"],
        flex="1",
    )

def deployment_configuration() -> rx.Component:
    """Deployment configuration options"""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.text("⚙️", font_size="1.25rem"),
                rx.text(
                    "Deployment Configuration",
                    font_size="1.125rem",
                    font_weight="600",
                    color=COLORS["primary"],
                ),
                spacing="3",
                align="center",
            ),
            
            rx.vstack(
                rx.hstack(
                    rx.text(
                        "Model Server:",
                        font_size="0.875rem",
                        font_weight="500",
                        color=COLORS["secondary"],
                    ),
                    rx.text(
                        settings.MODEL_SERVER_URL,
                        font_size="0.875rem",
                        color=COLORS["primary"],
                        font_family="monospace",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.hstack(
                    rx.text(
                        "Deployment Mode:",
                        font_size="0.875rem",
                        font_weight="500",
                        color=COLORS["secondary"],
                    ),
                    rx.text(
                        "Real-time Processing",
                        font_size="0.875rem",
                        color=COLORS["primary"],
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.hstack(
                    rx.text(
                        "Auto-restart:",
                        font_size="0.875rem",
                        font_weight="500",
                        color=COLORS["secondary"],
                    ),
                    rx.text(
                        "Enabled",
                        font_size="0.875rem",
                        color="green",
                    ),
                    spacing="2",
                    align="center",
                ),
                spacing="2",
                align="start",
                width="100%",
            ),
            
            spacing="3",
            align="start",
            width="100%",
        ),
        **card_variants["base"],
        width="100%",
    )

def deployment_status_display() -> rx.Component:
    """Display deployment status and progress"""
    return rx.cond(
        ModelDeploymentState.deployment_status != "",
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.cond(
                        ModelDeploymentState.is_deploying,
                        rx.spinner(size="2"),
                        rx.text("✅", font_size="1.25rem"),
                    ),
                    rx.text(
                        "Deployment Status",
                        font_size="1.125rem",
                        font_weight="600",
                        color=COLORS["primary"],
                    ),
                    spacing="3",
                    align="center",
                ),
                
                rx.text(
                    ModelDeploymentState.deployment_status,
                    font_size="1rem",
                    color=COLORS["secondary"],
                    text_align="center",
                ),
                
                spacing="3",
                align="center",
                width="100%",
            ),
            **card_variants["base"],
            width="100%",
            border=rx.cond(
                ModelDeploymentState.is_deploying,
                f"2px solid {COLORS['primary']}",
                f"2px solid green",
            ),
        ),
        rx.fragment(),
    )

def deployment_review() -> rx.Component:
    """Main deployment review component"""
    return rx.vstack(
        # Status messages
        status_banner(),
        
        # Review sections - responsive grid layout
        rx.box(
            rx.vstack(
                # Top row - cameras and model side by side
                rx.hstack(
                    selected_cameras_summary(),
                    selected_model_summary(),
                    spacing="4",
                    width="100%",
                    align="start",
                ),
                # Bottom row - configuration full width
                deployment_configuration(),
                spacing="4",
                width="100%",
            ),
            width="100%",
        ),
        
        # Deployment status
        deployment_status_display(),
        
        # Ready indicator - only show if no success message
        rx.cond(
            ModelDeploymentState.success != "",
            rx.fragment(),  # Don't show anything if there's a success message
            rx.cond(
                ModelDeploymentState.can_deploy,
                rx.card(
                    rx.hstack(
                        rx.text("🚀", font_size="1.25rem"),
                        rx.text(
                            "Ready to deploy!",
                            font_size="1.125rem",
                            font_weight="600",
                            color="green",
                        ),
                        rx.text(
                            "Click 'Deploy' to start the deployment process.",
                            font_size="0.875rem",
                            color=COLORS["text_muted"],
                        ),
                        spacing="3",
                        align="center",
                    ),
                    **{**card_variants["base"],
                    "width": "100%",
                    "padding": SPACING["md"],
                    "background": "rgba(0, 255, 0, 0.05)",
                    "border": f"2px solid green",
                    },
                   
                ),
                rx.cond(
                    ModelDeploymentState.is_deploying,
                    rx.fragment(),
                    rx.card(
                        rx.hstack(
                            rx.text("⚠️", font_size="1.25rem"),
                            rx.text(
                                "Missing selections",
                                font_size="1.125rem",
                                font_weight="600",
                                color="orange",
                            ),
                            rx.text(
                                "Please select a project, cameras, and a model before deploying.",
                                font_size="0.875rem",
                                color=COLORS["text_muted"],
                            ),
                            spacing="3",
                            align="center",
                        ),
                        **{**card_variants["base"],
                        "width": "100%",
                        "padding": SPACING["md"],
                        "background": "rgba(255, 165, 0, 0.05)",
                        "border": f"2px solid orange",
                        },
                    ),
                ),
            ),
        ),
        
        spacing="4",
        width="100%",
    )