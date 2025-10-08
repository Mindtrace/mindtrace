"""
Stepper component for multi-step workflows (with labels above circles and animated active state)
"""
import reflex as rx
from typing import List, Optional
from dataclasses import dataclass
from poseidon.components.image_components import (
    COLORS, TYPOGRAPHY, SIZING, SPACING, content_variants, button_variants, card_variants
)

@dataclass
class StepConfig:
    title: str
    description: str
    completed: bool = False
    active: bool = False
    content: Optional[rx.Component] = None


def step_indicator(step_number: int, is_active, is_past) -> rx.Component:
    return rx.box(
        rx.text(
            str(step_number),
            font_size="1rem",
            font_weight="600",
            color=rx.cond(is_active, "white", rx.cond(is_past, COLORS["primary"], COLORS["text_muted"])),
            transition="color .2s ease",
        ),
        width="2.5rem",
        height="2.5rem",
        border_radius="50%",
        background=rx.cond(is_active, COLORS["primary"], "transparent"),
        border=rx.cond(
            is_active,
            "none",
            rx.cond(is_past, f"2px solid {COLORS['primary']}", f"2px solid {COLORS['border']}")
        ),
        display="flex",
        align_items="center",
        justify_content="center",
        box_shadow=rx.cond(is_active, "0 0 0 6px rgba(0,87,255,.12)", "none"),
        transform=rx.cond(is_active, "scale(1.04)", "scale(1)"),
        transition="transform .2s ease, box-shadow .2s ease, background .2s ease, border-color .2s ease",
    )


def step_connector(is_filled) -> rx.Component:
    return rx.box(
        height="2px",
        flex="1",
        background=rx.cond(is_filled, COLORS["primary"], COLORS["border"]),
        transition="background-color .3s ease",
    )


def indicator_with_label(step_index: int, title: str, current_step_var) -> rx.Component:
    is_active = (current_step_var == (step_index + 1))
    is_past = (current_step_var > (step_index + 1))
    return rx.vstack(
        rx.text(
            title,
            font_size="0.8rem",
            font_weight="600",
            color=rx.cond(is_active, COLORS["primary"], COLORS["text_muted"]),
            margin_bottom="6px",
            text_align="center",
            white_space="nowrap",
        ),
        step_indicator(step_index + 1, is_active, is_past),
        spacing="0",
        align="center",
        min_width="120px",
    )


def step_header(step_number: int, title: str, description: str, is_active, is_past) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            step_indicator(step_number, is_active, is_past),
            rx.vstack(
                rx.text(
                    title,
                    font_size="1.125rem",
                    font_weight="600",
                    color=rx.cond(is_active, COLORS["primary"], COLORS["text_muted"]),
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


def step_content(content: rx.Component, is_active) -> rx.Component:
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
    can_proceed,
    on_next: callable,
    on_previous: callable,
    on_finish: callable,
    is_loading = False,
) -> rx.Component:
    return rx.hstack(
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
        # Reflex-safe counter (avoid f-strings with Vars)
        rx.hstack(
            rx.text("Step "),
            rx.text(current_step),
            rx.text(" of "),
            rx.text(total_steps),
            align="center",
            spacing="2",
            color=COLORS["text_muted"],
            style={"fontSize": "0.875rem", "fontWeight": "500"},
        ),
        rx.spacer(),
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
                rx.hstack(
                    rx.text("Finish", font_weight="500"),
                    rx.text("→", font_size="1rem"),
                    spacing="2",
                    align="center",
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
    current_step,
    on_next: callable,
    on_previous: callable,
    on_finish: callable,
    can_proceed = True,
    is_loading = False,
) -> rx.Component:
    total = len(steps)

    top_progress = rx.hstack(
        *[
            rx.hstack(
                indicator_with_label(i, step.title, current_step),
                rx.cond(
                    i < total - 1,
                    step_connector(current_step > (i + 1)),
                    rx.fragment(),
                ),
                spacing="4",
                align="center",
                flex="1" if i < total - 1 else "0",
            )
            for i, step in enumerate(steps)
        ],
        spacing="0",
        align="center",
        width="100%",
        margin_bottom=SPACING["lg"],
    )

    current_blocks = rx.vstack(
        *[
            rx.cond(
                current_step == i + 1,
                rx.vstack(
                    # step_header(
                    #     i + 1,
                    #     step.title,
                    #     step.description,
                    #     (current_step == i + 1),
                    #     (current_step > i + 1),
                    # ),
                    step_content(step.content or rx.fragment(), (current_step == i + 1)),
                    spacing="0",
                    width="100%",
                ),
                rx.fragment(),
            )
            for i, step in enumerate(steps)
        ],
        spacing="0",
        width="100%",
    )

    return rx.card(
        rx.vstack(
            top_progress,
            current_blocks,
            stepper_navigation(
                current_step,
                total,
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
