import reflex as rx
from poseidon.components_v2.containers.page_container import page_container
from poseidon.components.image_components import (
    COLORS,
    TYPOGRAPHY,
    SIZING,
    SPACING,
)
from poseidon.components_v2.core import button
from poseidon.components.stepper import stepper, StepConfig
from poseidon.components.deployments_dashboard import deployments_dashboard
from poseidon.components.camera_selection_grid import camera_selection_grid
from poseidon.components.model_selection_list import model_selection_list
from poseidon.components.deployment_review import deployment_review
from poseidon.state.model_deployment import ModelDeploymentState


def new_deployment_stepper() -> rx.Component:
    """Stepper component for new deployment workflow"""
    steps = [
        StepConfig(
            title="Select Project & Cameras",
            description="Choose project and cameras to deploy the model to",
            completed=ModelDeploymentState.step_1_completed,
            active=ModelDeploymentState.current_step == 1,
            content=camera_selection_grid(),
        ),
        StepConfig(
            title="Select Model",
            description="Choose the ML model to deploy",
            completed=ModelDeploymentState.step_2_completed,
            active=ModelDeploymentState.current_step == 2,
            content=model_selection_list(),
        ),
        StepConfig(
            title="Review & Deploy",
            description="Review selections and deploy the model",
            completed=ModelDeploymentState.step_3_completed,
            active=ModelDeploymentState.current_step == 3,
            content=deployment_review(),
        ),
    ]

    return stepper(
        steps=steps,
        current_step=ModelDeploymentState.current_step,
        on_next=ModelDeploymentState.next_step,
        on_previous=ModelDeploymentState.previous_step,
        on_finish=ModelDeploymentState.deploy_model,
        can_proceed=ModelDeploymentState.can_proceed_to_step,
        is_loading=ModelDeploymentState.is_deploying,
    )


def model_deployment_content() -> rx.Component:
    """Model deployment page content"""
    return page_container(
            # Loading state
            rx.cond(
                ModelDeploymentState.is_loading,
                rx.center(
                    rx.vstack(
                        rx.spinner(size="3"),
                        rx.text(
                            "Loading cameras and models...",
                            font_size="1rem",
                            color=COLORS["text_muted"],
                        ),
                        spacing="3",
                        align="center",
                    ),
                    padding=SPACING["xl"],
                    width="100%",
                ),
                # Page content
                rx.vstack(
                    # Active deployments dashboard
                    deployments_dashboard(),
                    # Divider
                    rx.divider(
                        size="4",
                        color_scheme="gray",
                        margin=SPACING["xl"],
                    ),
                    # New deployment section
                    rx.vstack(
                        rx.hstack(
                            rx.text(
                                "Create New Deployment",
                                font_size="1.5rem",
                                font_weight="600",
                                color=COLORS["primary"],
                            ),
                            rx.spacer(),
                            spacing="3",
                            align="center",
                            width="100%",
                        ),
                        # Stepper component
                        new_deployment_stepper(),
                        spacing="6",
                        width="100%",
                    ),
                    spacing="8",
                    width="100%",
                ),
            ),
    
        title="Model Deployment",
        sub_text="Deploy Brains to process camera feeds in real-time",
        tools=[
            button("Refresh", icon=rx.icon("refresh-ccw"), on_click=ModelDeploymentState.on_mount, variant="secondary", disabled=ModelDeploymentState.is_loading),
            button("Reset Stepper", icon=rx.icon("arrow-left"), on_click=ModelDeploymentState.reset_stepper, variant="secondary"),
        ],
        # Load data on mount
        on_mount=ModelDeploymentState.on_mount,
    )


def model_deployment_page() -> rx.Component:
    """Model Deployment page with three-step workflow"""
    return model_deployment_content()
