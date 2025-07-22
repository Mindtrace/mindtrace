import reflex as rx
from poseidon.components.image_components import (
    COLORS, TYPOGRAPHY, SIZING, SPACING, content_variants, button_variants, card_variants
)
from poseidon.state.model_deployment import ModelDeploymentState, ModelDict

def model_selection_card(model: rx.Var[ModelDict]) -> rx.Component:
    """Individual model selection card with selection indicator"""
    return rx.card(
        rx.vstack(
            # Header with selection indicator and model name
            rx.hstack(
                rx.box(
                    rx.cond(
                        ModelDeploymentState.selected_model_id == model.id,
                        rx.text("✓", color="green", font_weight="600"),
                        rx.text("○", color=COLORS["text_muted"]),
                    ),
                    width="1.5rem",
                    height="1.5rem",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                    border_radius="50%",
                    border=f"2px solid {COLORS['border']}",
                    background=rx.cond(
                        ModelDeploymentState.selected_model_id == model.id,
                        "rgba(0, 255, 0, 0.1)",
                        "transparent"
                    ),
                ),
                rx.vstack(
                    rx.text(
                        model.name,
                        font_weight="600",
                        font_size="1rem",
                        color=COLORS["primary"],
                    ),
                    rx.text(
                        f"v{model.version}",
                        font_size="0.875rem",
                        color=COLORS["text_muted"],
                    ),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                # Model type badge
                rx.badge(
                    model.type,
                    color_scheme="purple",
                    size="1",
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            
            # Model description
            rx.cond(
                model.description != "",
                rx.text(
                    model.description,
                    font_size="0.875rem",
                    color=COLORS["secondary"],
                    line_height="1.4",
                ),
                rx.fragment(),
            ),
            
            # Model details
            rx.hstack(
                rx.text(
                    f"🔧 {model.framework}",
                    font_size="0.75rem",
                    color=COLORS["text_muted"],
                ),
                rx.text(
                    f"✅ {model.validation_status}",
                    font_size="0.75rem",
                    color=rx.cond(
                        model.validation_status == "validated",
                        "green",
                        rx.cond(
                            model.validation_status == "pending",
                            "yellow",
                            "red"
                        )
                    ),
                ),
                spacing="3",
                align="center",
            ),
            
            spacing="3",
            align="start",
            width="100%",
        ),
        
        # Card styling
        **card_variants["base"],
        min_height="60px",
        width="100%",
        border=rx.cond(
            ModelDeploymentState.selected_model_id == model.id,
            f"2px solid {COLORS['primary']}",
            f"2px solid {COLORS['border']}",
        ),
        _hover={
            "box_shadow": "0 2px 8px rgba(0, 0, 0, 0.1)",
            "transform": "translateY(-1px)",
        },
        transition="all 0.2s ease",
        cursor="pointer",
        on_click=ModelDeploymentState.select_model(model.id),
    )

def model_selection_list() -> rx.Component:
    """List of model selection cards"""
    return rx.box(
        rx.vstack(
            # Header
            rx.hstack(
                rx.text(
                    "Select Model",
                    font_size="1.25rem",
                    font_weight="600",
                    color=COLORS["primary"],
                ),
                rx.spacer(),
                rx.cond(
                    ModelDeploymentState.selected_model_name != "",
                    rx.text(
                        f"Selected: {ModelDeploymentState.selected_model_name}",
                        font_size="0.875rem",
                        color=COLORS["primary"],
                        font_weight="500",
                    ),
                    rx.text(
                        "No model selected",
                        font_size="0.875rem",
                        color=COLORS["text_muted"],
                    ),
                ),
                width="100%",
                align="center",
            ),
            
            # Model list
            rx.cond(
                ModelDeploymentState.available_models.length() > 0,
                rx.vstack(
                    rx.foreach(
                        ModelDeploymentState.available_models,
                        model_selection_card,
                    ),
                    spacing="3",
                    width="100%",
                ),
                rx.center(
                    rx.vstack(
                        rx.box(
                            "🤖",
                            font_size="3rem",
                            color=COLORS["text_muted"],
                        ),
                        rx.text(
                            "No models available",
                            font_size="1.125rem",
                            font_weight="500",
                            color=COLORS["secondary"],
                        ),
                        rx.text(
                            "Create and register models to deploy them to cameras",
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