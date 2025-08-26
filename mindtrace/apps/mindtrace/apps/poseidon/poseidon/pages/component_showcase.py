"""Component Showcase Page - Demonstrates all components_v2 components."""

import reflex as rx

from poseidon.components_v2.branding import logo_poseidon
from poseidon.components_v2.containers import card, login_page_container
from poseidon.components_v2.core import button, button_group
from poseidon.components_v2.graphs.demo import (
    advanced_bar_chart_example,
    advanced_line_chart_example,
    advanced_pie_chart_example,
    defect_trends_example,
    simple_bar_chart_example,
    simple_line_chart_example,
    simple_pie_chart_example,
)
from poseidon.styles.global_styles import THEME as T


def component_showcase_page() -> rx.Component:
    """A showcase page demonstrating all components in components_v2."""

    return login_page_container(
        [
            rx.vstack(
                # Header
                logo_poseidon(),
                rx.heading(
                    "Component Showcase",
                    size="8",
                    color=T.colors.fg,
                    margin_bottom="4",
                ),
                rx.text(
                    "Token-based design system components",
                    size="4",
                    color=T.colors.fg_muted,
                    margin_bottom="8",
                ),
                card(
                    [
                        rx.vstack(
                            # Button Variants
                            rx.vstack(
                                rx.heading("Variants", size="4", color=T.colors.fg),
                                button_group(
                                    button("Primary", variant="primary"),
                                    button("Secondary", variant="secondary"),
                                    button("Ghost", variant="ghost"),
                                    button("Danger", variant="danger"),
                                    button("Outline", variant="outline"),
                                    spacing="3",
                                ),
                                spacing="3",
                                align_items="start",
                            ),
                            # Button Sizes
                            rx.vstack(
                                rx.heading("Sizes", size="4", color=T.colors.fg),
                                button_group(
                                    button("XS", size="xs"),
                                    button("SM", size="sm"),
                                    button("MD", size="md"),
                                    button("LG", size="lg"),
                                    spacing="3",
                                ),
                                spacing="3",
                                align_items="start",
                            ),
                            # Buttons with Icons
                            rx.vstack(
                                rx.heading("Buttons with Icons", size="4", color=T.colors.fg),
                                button_group(
                                    button("Save", icon="💾", variant="primary"),
                                    button("Download", icon="⬇️", icon_position="right", variant="secondary"),
                                    button("Loading", loading=True, variant="outline"),
                                    button("Disabled", disabled=True, variant="ghost"),
                                    spacing="3",
                                ),
                                spacing="3",
                                align_items="start",
                            ),
                            # Full Width Button
                            rx.vstack(
                                rx.heading("Full Width", size="4", color=T.colors.fg),
                                button("Full Width Button", full_width=True, variant="primary"),
                                spacing="3",
                                align_items="start",
                                width="100%",
                            ),
                            spacing="6",
                            width="100%",
                        ),
                    ]
                ),
                # Cards Section
                card(
                    [
                        rx.vstack(
                            rx.vstack(
                                rx.heading("Card Variants", size="4", color=T.colors.fg),
                                rx.hstack(
                                    # Default Card
                                    card(
                                        [
                                            rx.vstack(
                                                rx.text("Base", color=T.colors.fg_muted),
                                            ),
                                            button("Action", size="sm", variant="primary"),
                                        ]
                                    ),
                                    spacing="4",
                                    flex_wrap="wrap",
                                    width="100%",
                                ),
                                spacing="4",
                                align_items="start",
                                width="100%",
                            ),
                        ),
                    ]
                ),
                # Design Tokens Section
                card(
                    [
                        rx.vstack(
                            rx.vstack(
                                # Colors
                                rx.vstack(
                                    rx.heading("Colors", size="4", color=T.colors.fg),
                                    rx.hstack(
                                        rx.box(
                                            rx.text("Accent", color="white", size="1", weight="medium"),
                                            background=T.colors.accent,
                                            padding=T.spacing.space_3,
                                            border_radius=T.radius.r_md,
                                            min_width="80px",
                                            text_align="center",
                                        ),
                                        rx.box(
                                            rx.text("Success", color="white", size="1", weight="medium"),
                                            background=T.colors.success,
                                            padding=T.spacing.space_3,
                                            border_radius=T.radius.r_md,
                                            min_width="80px",
                                            text_align="center",
                                        ),
                                        rx.box(
                                            rx.text("Warning", color="white", size="1", weight="medium"),
                                            background=T.colors.warning,
                                            padding=T.spacing.space_3,
                                            border_radius=T.radius.r_md,
                                            min_width="80px",
                                            text_align="center",
                                        ),
                                        rx.box(
                                            rx.text("Danger", color="white", size="1", weight="medium"),
                                            background=T.colors.danger,
                                            padding=T.spacing.space_3,
                                            border_radius=T.radius.r_md,
                                            min_width="80px",
                                            text_align="center",
                                        ),
                                        spacing="2",
                                        flex_wrap="wrap",
                                    ),
                                    spacing="3",
                                    align_items="start",
                                ),
                                # Typography
                                rx.vstack(
                                    rx.heading("Typography", size="4", color=T.colors.fg),
                                    rx.vstack(
                                        rx.text("Heading 1", size="8", weight="bold", color=T.colors.fg),
                                        rx.text("Heading 2", size="6", weight="bold", color=T.colors.fg),
                                        rx.text("Heading 3", size="4", weight="medium", color=T.colors.fg),
                                        rx.text("Body text - regular weight", size="3", color=T.colors.fg),
                                        rx.text("Muted text for secondary content", size="3", color=T.colors.fg_muted),
                                        rx.text("Subtle text for hints and labels", size="2", color=T.colors.fg_subtle),
                                        spacing="2",
                                        align_items="start",
                                    ),
                                    spacing="3",
                                    align_items="start",
                                ),
                                # Spacing
                                rx.vstack(
                                    rx.heading("Spacing Scale", size="4", color=T.colors.fg),
                                    rx.hstack(
                                        rx.box(
                                            rx.text("1", size="1", color="white"),
                                            background=T.colors.accent,
                                            height="1",
                                            min_width="40px",
                                            display="flex",
                                            align_items="center",
                                            justify_content="center",
                                            border_radius=T.radius.r_sm,
                                        ),
                                        rx.box(
                                            rx.text("2", size="1", color="white"),
                                            background=T.colors.accent,
                                            height="2",
                                            min_width="40px",
                                            display="flex",
                                            align_items="center",
                                            justify_content="center",
                                            border_radius=T.radius.r_sm,
                                        ),
                                        rx.box(
                                            rx.text("3", size="1", color="white"),
                                            background=T.colors.accent,
                                            height="3",
                                            min_width="40px",
                                            display="flex",
                                            align_items="center",
                                            justify_content="center",
                                            border_radius=T.radius.r_sm,
                                        ),
                                        rx.box(
                                            rx.text("4", size="1", color="white"),
                                            background=T.colors.accent,
                                            height="4",
                                            min_width="40px",
                                            display="flex",
                                            align_items="center",
                                            justify_content="center",
                                            border_radius=T.radius.r_sm,
                                        ),
                                        rx.box(
                                            rx.text("6", size="1", color="white"),
                                            background=T.colors.accent,
                                            height="6",
                                            min_width="40px",
                                            display="flex",
                                            align_items="center",
                                            justify_content="center",
                                            border_radius=T.radius.r_sm,
                                        ),
                                        spacing="2",
                                        flex_wrap="wrap",
                                    ),
                                    spacing="3",
                                    align_items="start",
                                ),
                                spacing="6",
                                align_items="start",
                                width="100%",
                            ),
                        ),
                    ]
                ),
                # Interactive States
                card(
                    [
                        rx.vstack(
                            rx.vstack(
                                rx.heading("Button States", size="4", color=T.colors.fg),
                                rx.hstack(
                                    button("Normal", variant="primary"),
                                    button("Loading", variant="primary", loading=True),
                                    button("Disabled", variant="primary", disabled=True),
                                    spacing="3",
                                ),
                                rx.text(
                                    "states.",
                                    size="2",
                                    color=T.colors.fg_muted,
                                ),
                                spacing="4",
                                align_items="start",
                                width="100%",
                            ),
                        ),
                    ]
                ),
                # Charts Section
                card(
                    [
                        rx.vstack(
                            rx.heading("Charts", size="4", color=T.colors.fg),
                            rx.text(
                                "Interactive charts with various configurations",
                                size="2",
                                color=T.colors.fg_muted,
                            ),
                            # Pie Charts
                            rx.vstack(
                                rx.heading("Pie Charts", size="3", color=T.colors.fg),
                                rx.hstack(
                                    simple_pie_chart_example(),
                                    advanced_pie_chart_example(),
                                    spacing="6",
                                    flex_wrap="wrap",
                                    width="100%",
                                ),
                                spacing="4",
                                align_items="start",
                                width="100%",
                            ),
                            # Line Charts
                            rx.vstack(
                                rx.heading("Line Charts", size="3", color=T.colors.fg),
                                rx.hstack(
                                    simple_line_chart_example(),
                                    advanced_line_chart_example(),
                                    spacing="6",
                                    flex_wrap="wrap",
                                    width="100%",
                                ),
                                spacing="4",
                                align_items="start",
                                width="100%",
                            ),
                            # Bar Charts
                            rx.vstack(
                                rx.heading("Bar Charts", size="3", color=T.colors.fg),
                                rx.hstack(
                                    simple_bar_chart_example(),
                                    defect_trends_example(),
                                    spacing="6",
                                    flex_wrap="wrap",
                                    width="100%",
                                ),
                                rx.hstack(
                                    advanced_bar_chart_example(),
                                    spacing="6",
                                    flex_wrap="wrap",
                                    width="100%",
                                ),
                                spacing="4",
                                align_items="start",
                                width="100%",
                            ),
                            spacing="6",
                            align_items="start",
                            width="100%",
                        ),
                    ]
                ),
                max_width="1200px",
                width="100%",
                spacing="6",
            )
        ]
    )
