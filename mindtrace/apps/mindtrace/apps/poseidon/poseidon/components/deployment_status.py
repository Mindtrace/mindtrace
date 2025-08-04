import reflex as rx
from poseidon.components.image_components import (
    COLORS, TYPOGRAPHY, SIZING, SPACING, content_variants, button_variants, card_variants
)
from poseidon.components.status_banner import status_banner
from poseidon.state.model_deployment import ModelDeploymentState, DeploymentDict

def deployment_card(deployment: rx.Var[DeploymentDict]) -> rx.Component:
    """Individual deployment card"""
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.text(
                    f"Model: {deployment.model_id}",
                    font_size="0.875rem",
                    font_weight="500",
                    color=COLORS["primary"],
                ),
                rx.text(
                    rx.cond(
                        deployment.camera_ids != [],
                        f"Multiple cameras",
                        "No cameras"
                    ),
                    font_size="0.75rem",
                    color=COLORS["secondary"],
                ),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.badge(
                deployment.deployment_status,
                color_scheme=rx.cond(
                    deployment.deployment_status == "deployed",
                    "green",
                    rx.cond(
                        deployment.deployment_status == "pending",
                        "yellow",
                        "red"
                    )
                ),
                size="1",
            ),
            rx.button(
                "Undeploy",
                on_click=ModelDeploymentState.undeploy_model(deployment.id),
                **button_variants["secondary"],
                size="1",
            ),
            spacing="3",
            align="center",
            width="100%",
        ),
        padding=SPACING["sm"],
        border=f"1px solid {COLORS['border']}",
        border_radius="6px",
        _hover={"bg": COLORS["background"]},
    )

def deployment_button() -> rx.Component:
    """Deploy button with loading state"""
    return rx.button(
        rx.cond(
            ModelDeploymentState.is_deploying,
            rx.hstack(
                rx.spinner(size="2"),
                rx.text("Deploying...", font_weight="500"),
                spacing="2",
                align="center",
            ),
            rx.hstack(
                rx.text("🚀", font_size="1rem"),
                rx.text("Deploy Model", font_weight="500"),
                spacing="2",
                align="center",
            ),
        ),
        on_click=ModelDeploymentState.deploy_model,
        disabled=~ModelDeploymentState.can_deploy | ModelDeploymentState.is_deploying,
        **{
            **button_variants["primary"],
            "size": "3",
            "width": "100%",
            "_hover": {
                **button_variants["primary"].get("_hover", {}),
                "transform": rx.cond(
                    ModelDeploymentState.can_deploy & ~ModelDeploymentState.is_deploying,
                    "translateY(-1px)",
                    "none"
                ),
                "box_shadow": rx.cond(
                    ModelDeploymentState.can_deploy & ~ModelDeploymentState.is_deploying,
                    "0 4px 12px rgba(0, 0, 0, 0.15)",
                    "none"
                ),
            }
        },
        transition="all 0.2s ease",
    )

def deployment_summary() -> rx.Component:
    """Summary of deployment selections"""
    return rx.card(
        rx.vstack(
            rx.text(
                "Deployment Summary",
                font_size="1.125rem",
                font_weight="600",
                color=COLORS["primary"],
            ),
            
            # Camera selection summary
            rx.hstack(
                rx.text(
                    "📷",
                    font_size="1.25rem",
                ),
                rx.vstack(
                    rx.text(
                        "Selected Cameras",
                        font_size="0.875rem",
                        color=COLORS["text_muted"],
                    ),
                    rx.text(
                        f"{ModelDeploymentState.selected_cameras_count} cameras",
                        font_size="1rem",
                        font_weight="500",
                        color=COLORS["primary"],
                    ),
                    spacing="1",
                    align="start",
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            
            # Model selection summary
            rx.hstack(
                rx.text(
                    "🤖",
                    font_size="1.25rem",
                ),
                rx.vstack(
                    rx.text(
                        "Selected Model",
                        font_size="0.875rem",
                        color=COLORS["text_muted"],
                    ),
                    rx.text(
                        rx.cond(
                            ModelDeploymentState.selected_model_name != "",
                            ModelDeploymentState.selected_model_name,
                            "No model selected"
                        ),
                        font_size="1rem",
                        font_weight="500",
                        color=rx.cond(
                            ModelDeploymentState.selected_model_name != "",
                            COLORS["primary"],
                            COLORS["text_muted"]
                        ),
                    ),
                    spacing="1",
                    align="start",
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            
            # Deployment readiness
            rx.hstack(
                rx.text(
                    rx.cond(
                        ModelDeploymentState.can_deploy,
                        "✅",
                        "❌"
                    ),
                    font_size="1.25rem",
                ),
                rx.text(
                    rx.cond(
                        ModelDeploymentState.can_deploy,
                        "Ready to deploy",
                        "Select cameras and model to deploy"
                    ),
                    font_size="1rem",
                    font_weight="500",
                    color=rx.cond(
                        ModelDeploymentState.can_deploy,
                        "green",
                        COLORS["text_muted"]
                    ),
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            
            spacing="4",
            width="100%",
        ),
        **card_variants["base"],
    )

def deployment_status_display() -> rx.Component:
    """Display deployment status during deployment"""
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
            border=rx.cond(
                ModelDeploymentState.is_deploying,
                f"2px solid {COLORS['primary']}",
                f"2px solid green",
            ),
        ),
        rx.fragment(),
    )

def active_deployments() -> rx.Component:
    """Display active deployments"""
    return rx.cond(
        ModelDeploymentState.active_deployments.length() > 0,
        rx.card(
            rx.vstack(
                rx.text(
                    "Active Deployments",
                    font_size="1.125rem",
                    font_weight="600",
                    color=COLORS["primary"],
                ),
                
                rx.foreach(
                    ModelDeploymentState.active_deployments,
                    deployment_card,
                ),
                
                spacing="3",
                width="100%",
            ),
            **card_variants["base"],
        ),
        rx.fragment(),
    )

def deployment_status() -> rx.Component:
    """Main deployment status component"""
    return rx.vstack(
        # Status messages
        status_banner(),
        
        # Deployment summary
        deployment_summary(),
        
        # Deploy button
        deployment_button(),
        
        # Deployment status display
        deployment_status_display(),
        
        # Active deployments
        active_deployments(),
        
        spacing="4",
        width="100%",
    )