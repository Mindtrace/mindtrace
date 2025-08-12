"""
Deployments dashboard component for managing active model deployments
"""
import reflex as rx
from poseidon.components.image_components import (
    COLORS, TYPOGRAPHY, SIZING, SPACING, content_variants, button_variants, card_variants
)
from poseidon.components_v2.core import button
from poseidon.state.model_deployment import ModelDeploymentState, DeploymentDict

def deployment_status_badge(status: str) -> rx.Component:
    """Status badge for deployment"""
    return rx.badge(
        status.capitalize(),
        color_scheme=rx.cond(
            status == "deployed",
            "green",
            rx.cond(
                status == "pending",
                "yellow",
                rx.cond(
                    status == "deploying",
                    "blue",
                    "red"
                )
            )
        ),
        size="1",
        variant="solid",
    )

def deployment_health_indicator(health: str) -> rx.Component:
    """Health indicator for deployment"""
    return rx.hstack(
        rx.box(
            width="8px",
            height="8px",
            border_radius="50%",
            background=rx.cond(
                health == "healthy",
                "green",
                rx.cond(
                    health == "warning",
                    "yellow",
                    "red"
                )
            ),
        ),
        rx.text(
            health.capitalize(),
            font_size="0.75rem",
            color=COLORS["text_muted"],
            font_weight="500",
        ),
        spacing="2",
        align="center",
    )

def deployment_actions(deployment_id: str) -> rx.Component:
    """Action buttons for deployment"""
    return rx.hstack(
        button(
            text="📊",
            variant="ghost",
            size="1",
            padding="0.25rem",
            title="View metrics",
        ),
        button(
            text="📝",
            variant="ghost",
            size="1",
            padding="0.25rem",
            title="View logs",
        ),
        button(
            text="⚙️",
            variant="ghost",
            size="1",
            padding="0.25rem",
            title="Settings",
        ),
        button(
            text="🗑️",
            on_click=ModelDeploymentState.undeploy_model(deployment_id),
            variant="ghost",
            size="1",
            padding="0.25rem",
            title="Undeploy",
            #_hover={"color": "red"},
        ),
        spacing="1",
        align="center",
    )

def deployment_card(deployment: rx.Var[DeploymentDict]) -> rx.Component:
    """Individual deployment card"""
    return rx.card(
        rx.vstack(
            # Header with model info and status
            rx.hstack(
                rx.vstack(
                    rx.text(
                        f"Model: {deployment.model_id}",
                        font_size="1rem",
                        font_weight="600",
                        color=COLORS["primary"],
                    ),
                    rx.text(
                        f"Deployed: {deployment.created_at}",
                        font_size="0.75rem",
                        color=COLORS["text_muted"],
                    ),
                    spacing="1",
                    align="start",
                    flex="1",
                ),
                rx.vstack(
                    deployment_status_badge(deployment.deployment_status),
                    deployment_health_indicator(deployment.health_status),
                    spacing="2",
                    align="end",
                ),
                spacing="3",
                align="start",
                width="100%",
            ),
            
            # Camera info
            rx.hstack(
                rx.text(
                    "📷",
                    font_size="1rem",
                ),
                rx.text(
                    f"{deployment.camera_ids.length()} cameras",
                    font_size="0.875rem",
                    color=COLORS["secondary"],
                    font_weight="500",
                ),
                spacing="2",
                align="center",
            ),
            
            # Actions
            rx.hstack(
                deployment_actions(deployment.id),
                rx.spacer(),
                rx.text(
                    f"ID: {deployment.id}",
                    font_size="0.75rem",
                    color=COLORS["text_muted"],
                    font_family="monospace",
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            
            spacing="3",
            align="start",
            width="100%",
        ),
        **card_variants["base"],
        _hover={
            "box_shadow": "0 4px 12px rgba(0, 0, 0, 0.1)",
            "transform": "translateY(-1px)",
        },
        transition="all 0.2s ease",
    )

def deployment_stats() -> rx.Component:
    """Deployment statistics overview"""
    return rx.hstack(
        rx.card(
            rx.vstack(
                rx.text(
                    ModelDeploymentState.active_deployments.length(),
                    font_size="2rem",
                    font_weight="700",
                    color=COLORS["primary"],
                ),
                rx.text(
                    "Active Deployments",
                    font_size="0.875rem",
                    color=COLORS["text_muted"],
                    text_align="center",
                ),
                spacing="1",
                align="center",
            ),
            **card_variants["base"],
            text_align="center",
            flex="1",
        ),
        rx.card(
            rx.vstack(
                rx.text(
                    ModelDeploymentState.available_cameras.length(),
                    font_size="2rem",
                    font_weight="700",
                    color="green",
                ),
                rx.text(
                    "Available Cameras",
                    font_size="0.875rem",
                    color=COLORS["text_muted"],
                    text_align="center",
                ),
                spacing="1",
                align="center",
            ),
            **card_variants["base"],
            text_align="center",
            flex="1",
        ),
        rx.card(
            rx.vstack(
                rx.text(
                    ModelDeploymentState.available_models.length(),
                    font_size="2rem",
                    font_weight="700",
                    color="blue",
                ),
                rx.text(
                    "Available Models",
                    font_size="0.875rem",
                    color=COLORS["text_muted"],
                    text_align="center",
                ),
                spacing="1",
                align="center",
            ),
            **card_variants["base"],
            text_align="center",
            flex="1",
        ),
        spacing="4",
        width="100%",
    )

def deployments_dashboard() -> rx.Component:
    """Main deployments dashboard"""
    return rx.vstack(
        # Header
        rx.hstack(
            rx.text(
                "Active Deployments",
                font_size="1.5rem",
                font_weight="600",
                color=COLORS["primary"],
            ),
            rx.spacer(),
            rx.hstack(
                button(
                    text="🔄",
                    variant="secondary",
                    on_click=ModelDeploymentState.load_deployments,
                    size="sm",
                    disabled=ModelDeploymentState.is_loading,
                ),
                button(
                    text="New Deployment",
                    variant="primary",
                    size="sm",
                ),
                spacing="2",
            ),
            spacing="3",
            align="center",
            width="100%",
        ),
        
        # Statistics
        deployment_stats(),
        
        # Deployments grid
        rx.cond(
            ModelDeploymentState.is_loading,
            rx.center(
                rx.vstack(
                    rx.spinner(size="3"),
                    rx.text(
                        "Loading deployments...",
                        font_size="1rem",
                        color=COLORS["text_muted"],
                    ),
                    spacing="3",
                    align="center",
                ),
                padding=SPACING["xl"],
                width="100%",
            ),
            rx.cond(
                ModelDeploymentState.active_deployments.length() > 0,
                rx.box(
                    rx.foreach(
                        ModelDeploymentState.active_deployments,
                        deployment_card,
                    ),
                    display="grid",
                    grid_template_columns="repeat(auto-fill, minmax(400px, 1fr))",
                    gap=SPACING["md"],
                    width="100%",
                ),
                rx.center(
                    rx.vstack(
                        rx.box(
                            "🚀",
                            font_size="3rem",
                            color=COLORS["text_muted"],
                        ),
                        rx.text(
                            "No active deployments",
                            font_size="1.25rem",
                            font_weight="600",
                            color=COLORS["secondary"],
                        ),
                        rx.text(
                            "Create your first deployment using the stepper below",
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
        ),
        
        spacing="6",
        width="100%",
    )