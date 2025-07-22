"""
Stepper component for multi-step workflows
"""
import reflex as rx
from typing import List, Optional
from dataclasses import dataclass
from poseidon.components.image_components import (
    COLORS, TYPOGRAPHY, SIZING, SPACING, content_variants, button_variants, card_variants
)

@dataclass
class StepConfig:
    """Configuration for a single step"""
    title: str
    description: str
    completed: bool = False
    active: bool = False
    content: Optional[rx.Component] = None

def step_indicator(step_number: int, is_active: bool, is_completed: bool) -> rx.Component:
    """Individual step indicator circle"""
    return rx.box(
        rx.cond(
            is_completed,
            rx.text("✓", font_size="1rem", font_weight="600", color="white"),
            rx.text(str(step_number), font_size="1rem", font_weight="600", color="white"),
        ),
        width="2.5rem",
        height="2.5rem",
        border_radius="50%",
        background=rx.cond(
            is_completed,
            "green",
            rx.cond(
                is_active,
                COLORS["primary"],
                COLORS["text_muted"]
            )
        ),
        display="flex",
        align_items="center",
        justify_content="center",
        border=rx.cond(
            is_active & ~is_completed,
            f"3px solid {COLORS['primary']}",
            "none"
        ),
        transition="all 0.3s ease",
    )

def step_connector(is_completed: bool) -> rx.Component:
    """Line connector between steps"""
    return rx.box(
        height="2px",
        flex="1",
        background=rx.cond(
            is_completed,
            "green",
            COLORS["border"]
        ),
        transition="all 0.3s ease",
    )

def step_header(step_number: int, title: str, description: str, is_active: bool, is_completed: bool) -> rx.Component:
    """Step header with indicator and text"""
    return rx.vstack(
        rx.hstack(
            step_indicator(step_number, is_active, is_completed),
            rx.vstack(
                rx.text(
                    title,
                    font_size="1.125rem",
                    font_weight="600",
                    color=rx.cond(
                        is_active,
                        COLORS["primary"],
                        rx.cond(
                            is_completed,
                            "green",
                            COLORS["text_muted"]
                        )
                    ),
                ),
                rx.text(
                    description,
                    font_size="0.875rem",
                    color=COLORS["text_muted"],
                    line_height="1.4",
                ),
                spacing="1",
                align="start",
                flex="1",
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        spacing="2",
        width="100%",
    )

def step_content(content: rx.Component, is_active: bool) -> rx.Component:
    """Step content area"""
    return rx.cond(
        is_active,
        rx.box(
            content,
            padding=SPACING["sm"],
            border_radius=SIZING["border_radius"],
            background=COLORS["background"],
            border=f"1px solid {COLORS['border']}",
            margin_top=SPACING["sm"],
            min_height="400px",
            max_height="600px",
            overflow_y="auto",
            width="100%",
        ),
        rx.fragment(),
    )

def stepper_navigation(
    current_step: int,
    total_steps: int,
    can_proceed: bool,
    on_next: callable,
    on_previous: callable,
    on_finish: callable,
    is_loading: bool = False
) -> rx.Component:
    """Navigation buttons for stepper"""
    return rx.hstack(
        # Previous button
        rx.cond(
            current_step > 1,
            rx.button(
                rx.hstack(
                    rx.text("←", font_size="1rem"),
                    rx.text("Previous", font_weight="500"),
                    spacing="2",
                    align="center",
                ),
                on_click=on_previous,
                **button_variants["secondary"],
                disabled=is_loading,
            ),
            rx.fragment(),
        ),
        
        rx.spacer(),
        
        # Step counter
        rx.text(
            f"Step {current_step} of {total_steps}",
            font_size="0.875rem",
            color=COLORS["text_muted"],
            font_weight="500",
        ),
        
        rx.spacer(),
        
        # Next/Finish button
        rx.cond(
            current_step < total_steps,
            rx.button(
                rx.hstack(
                    rx.text("Next", font_weight="500"),
                    rx.text("→", font_size="1rem"),
                    spacing="2",
                    align="center",
                ),
                on_click=on_next,
                **button_variants["primary"],
                disabled=~can_proceed | is_loading,
            ),
            rx.button(
                rx.cond(
                    is_loading,
                    rx.hstack(
                        rx.spinner(size="2"),
                        rx.text("Deploying...", font_weight="500"),
                        spacing="2",
                        align="center",
                    ),
                    rx.hstack(
                        rx.text("🚀", font_size="1rem"),
                        rx.text("Deploy", font_weight="500"),
                        spacing="2",
                        align="center",
                    ),
                ),
                on_click=on_finish,
                **button_variants["primary"],
                disabled=~can_proceed | is_loading,
            ),
        ),
        
        justify="between",
        align="center",
        width="100%",
        padding=SPACING["md"],
        border_top=f"1px solid {COLORS['border']}",
        margin_top=SPACING["lg"],
    )

def stepper(
    steps: List[StepConfig],
    current_step: int,
    on_next: callable,
    on_previous: callable,
    on_finish: callable,
    can_proceed: bool = True,
    is_loading: bool = False,
) -> rx.Component:
    """Main stepper component"""
    return rx.card(
        rx.vstack(
            # Steps header with progress indicators
            rx.hstack(
                *[
                    rx.hstack(
                        step_indicator(
                            i + 1,
                            current_step == i + 1,
                            step.completed
                        ),
                        rx.cond(
                            i < len(steps) - 1,
                            step_connector(step.completed),
                            rx.fragment(),
                        ),
                        spacing="0",
                        align="center",
                        flex="1" if i < len(steps) - 1 else "0",
                    )
                    for i, step in enumerate(steps)
                ],
                spacing="0",
                align="center",
                width="100%",
                margin_bottom=SPACING["lg"],
            ),
            
            # Current step content
            rx.vstack(
                *[
                    rx.cond(
                        current_step == i + 1,
                        rx.vstack(
                            step_header(
                                i + 1,
                                step.title,
                                step.description,
                                current_step == i + 1,
                                step.completed
                            ),
                            step_content(
                                step.content or rx.fragment(),
                                current_step == i + 1
                            ),
                            spacing="0",
                            width="100%",
                        ),
                        rx.fragment(),
                    )
                    for i, step in enumerate(steps)
                ],
                spacing="0",
                width="100%",
            ),
            
            # Navigation
            stepper_navigation(
                current_step,
                len(steps),
                can_proceed,
                on_next,
                on_previous,
                on_finish,
                is_loading,
            ),
            
            spacing="0",
            width="100%",
        ),
        **{**card_variants["base"], "padding": SPACING["lg"]},
        width="100%",
        
    )