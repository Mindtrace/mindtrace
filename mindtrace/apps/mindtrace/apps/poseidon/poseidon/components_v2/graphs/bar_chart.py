"""
Bar Chart Component for Poseidon

A beautiful, responsive bar chart component that follows the app's design system.
Supports both simple and advanced configurations with custom styling.
"""

from typing import Any, Dict, List, Optional, Union

import reflex as rx

from poseidon.styles.global_styles import THEME as T

# Poseidon Color Palette for Charts
CHART_COLORS = [
    "#0057FF",  # Primary blue
    "#0EA5E9",  # Secondary sky blue
    "#10B981",  # Success green
    "#F59E0B",  # Warning amber
    "#EF4444",  # Error red
    "#8B5CF6",  # Purple
    "#06B6D4",  # Cyan
    "#84CC16",  # Lime
    "#F97316",  # Orange
    "#EC4899",  # Pink
    "#6366F1",  # Indigo
    "#14B8A6",  # Teal
]


def get_chart_colors(count: int) -> List[str]:
    """Get a list of colors for the chart based on the number of data series."""
    if count <= len(CHART_COLORS):
        return CHART_COLORS[:count]

    # If we need more colors, generate them by cycling through the base colors
    colors = []
    for i in range(count):
        base_color = CHART_COLORS[i % len(CHART_COLORS)]
        # Add some variation by adjusting opacity
        opacity = 0.7 + (0.3 * (i // len(CHART_COLORS)))
        colors.append(f"{base_color}{int(opacity * 255):02x}")

    return colors


def bar_chart(
    data: List[Dict[str, Any]],
    x_key: str = "x",
    y_key: str = "y",
    y_keys: Optional[List[str]] = None,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    width: Union[str, int] = "100%",
    height: Union[str, int] = 300,
    show_grid: bool = True,
    show_legend: bool = True,
    show_tooltip: bool = True,
    layout: str = "horizontal",
    bar_size: Optional[int] = None,
    bar_gap: Union[str, int] = 4,
    bar_category_gap: Union[str, int] = "10%",
    animate: bool = True,
    **kwargs,
) -> rx.Component:
    """
    Create a beautiful bar chart component.

    Args:
        data: List of dictionaries containing the data
        x_key: Key for the x-axis values
        y_key: Key for the y-axis values (single series)
        y_keys: List of keys for multiple y-axis values (multiple series)
        title: Chart title
        subtitle: Chart subtitle
        width: Chart width
        height: Chart height
        show_grid: Whether to show grid lines
        show_legend: Whether to show legend
        show_tooltip: Whether to show tooltip on hover
        layout: Chart layout ("horizontal" or "vertical")
        bar_size: Size of bars in pixels
        bar_gap: Gap between bars in the same category
        bar_category_gap: Gap between bar categories
        animate: Whether to animate the chart
        **kwargs: Additional props for the chart

    Returns:
        A Reflex component containing the bar chart
    """

    # Create chart components
    chart_components = []

    # Add grid if requested
    if show_grid:
        chart_components.append(
            rx.recharts.cartesian_grid(
                stroke_dasharray="3 3",
                stroke=T.colors.border,
                stroke_opacity=0.3,
            )
        )

    # Add x-axis
    if layout == "horizontal":
        chart_components.append(
            rx.recharts.x_axis(
                data_key=x_key,
                stroke=T.colors.fg_muted,
                tick_line=False,
                axis_line=False,
                tick_margin=10,
            )
        )
        chart_components.append(
            rx.recharts.y_axis(
                stroke=T.colors.fg_muted,
                tick_line=False,
                axis_line=False,
                tick_margin=10,
            )
        )
    else:
        # Vertical layout
        chart_components.append(
            rx.recharts.x_axis(
                type_="number",
                stroke=T.colors.fg_muted,
                tick_line=False,
                axis_line=False,
                tick_margin=10,
            )
        )
        chart_components.append(
            rx.recharts.y_axis(
                data_key=x_key,
                type_="category",
                stroke=T.colors.fg_muted,
                tick_line=False,
                axis_line=False,
                tick_margin=10,
            )
        )

    # Handle single series vs multiple series
    if y_keys and len(y_keys) > 1:
        # Multiple y_keys - create a bar for each key
        colors = get_chart_colors(len(y_keys))
        for i, key in enumerate(y_keys):
            chart_components.append(
                rx.recharts.bar(
                    data_key=key,
                    stroke=colors[i],
                    fill=colors[i],
                    stroke_width=1,
                    name=key.title(),
                    radius=[4, 4, 0, 0] if layout == "horizontal" else [0, 4, 4, 0],
                )
            )
    else:
        # Single series
        chart_components.append(
            rx.recharts.bar(
                data_key=y_key,
                stroke=CHART_COLORS[0],
                fill=CHART_COLORS[0],
                stroke_width=1,
                radius=[4, 4, 0, 0] if layout == "horizontal" else [0, 4, 4, 0],
            )
        )

    # Add tooltip if requested
    if show_tooltip:
        chart_components.append(
            rx.recharts.graphing_tooltip(
                content_style={
                    "background": T.colors.surface,
                    "border": f"1px solid {T.colors.border}",
                    "border_radius": T.radius.r_md,
                    "box_shadow": T.shadows.shadow_1,
                    "backdrop_filter": T.effects.backdrop_filter,
                    "padding": T.spacing.space_4,
                    "padding_bottom": 0,
                    "font_family": T.typography.font_sans,
                    "font_size": T.typography.fs_sm,
                    "color": T.colors.fg,
                }
            )
        )

    # Add legend if requested
    if show_legend:
        chart_components.append(
            rx.recharts.legend(
                vertical_align="top",
                height=36,
                wrapper_style={
                    "padding_bottom": T.spacing.space_4,
                    "font_family": T.typography.font_sans,
                    "font_size": T.typography.fs_sm,
                    "color": T.colors.fg_muted,
                },
            )
        )

    # Create the chart container
    chart_container = rx.recharts.bar_chart(
        *chart_components,
        data=data,
        layout=layout,
        bar_size=bar_size,
        bar_gap=bar_gap,
        bar_category_gap=bar_category_gap,
        width=width,
        height=height,
        margin={"top": 20, "right": 20, "bottom": 20, "left": 20},
        **kwargs,
    )

    # Always wrap in a container for consistency
    title_component = (
        rx.text(
            title,
            font_size=T.typography.fs_xl,
            font_weight=T.typography.fw_600,
            color=T.colors.fg,
            text_align="center",
        )
        if title
        else None
    )

    subtitle_component = (
        rx.text(
            subtitle,
            font_size=T.typography.fs_sm,
            color=T.colors.fg_muted,
            text_align="center",
        )
        if subtitle
        else None
    )

    return rx.vstack(
        rx.vstack(
            title_component,
            subtitle_component,
            spacing="1",
        ),
        chart_container,
        spacing="1",
        width="100%",
    )


def chart_card(
    title: str,
    subtitle: Optional[str] = None,
    children: Optional[rx.Component] = None,
    card_variant: str = "default",
) -> rx.Component:
    """
    Create a card container for charts or other components.

    Args:
        title: Card title
        subtitle: Card subtitle
        children: The component to be wrapped in the card (e.g., a chart)
        card_variant: Card styling variant

    Returns:
        A Reflex component containing the children in a card
    """

    # Card styles based on variant
    card_styles = {
        "background": T.colors.surface,
        "backdrop_filter": T.effects.backdrop_filter,
        "border_radius": T.radius.r_xl,
        "border": f"1px solid {T.colors.border}",
        "box_shadow": T.shadows.shadow_2,
        "padding": T.spacing.space_4,
        "padding_bottom": 0,
        "position": "relative",
        "overflow": "hidden",
        "transition": T.motion.dur,
    }

    # Add hover effects for interactive cards
    if card_variant == "interactive":
        card_styles.update(
            {
                "_hover": {
                    "transform": "translateY(-4px)",
                    "box_shadow": T.shadows.shadow_2,
                    "border_color": T.colors.accent,
                }
            }
        )

    # Create the card container
    return rx.box(
        rx.vstack(
            rx.vstack(
                rx.text(
                    title,
                    font_size=T.typography.fs_lg,
                    font_weight=T.typography.fw_600,
                    color=T.colors.fg,
                    text_align="center",
                ),
                rx.text(
                    subtitle,
                    font_size=T.typography.fs_sm,
                    color=T.colors.fg_muted,
                    text_align="center",
                )
                if subtitle
                else None,
                spacing="1",
            ),
            children,
            spacing="1",
            width="100%",
        ),
        style=card_styles,
        width="100%",
    )


def bar_chart_card(
    title: str,
    subtitle: Optional[str] = None,
    children: Optional[rx.Component] = None,
    card_variant: str = "default",
) -> rx.Component:
    """
    Create a bar chart wrapped in a beautiful card container.

    Args:
        title: Card title
        subtitle: Card subtitle
        children: The component to be wrapped in the card (e.g., a chart)
        card_variant: Card styling variant

    Returns:
        A Reflex component containing the children in a card
    """

    # Card styles based on variant
    card_styles = {
        "background": T.colors.surface,
        "backdrop_filter": T.effects.backdrop_filter,
        "border_radius": T.radius.r_xl,
        "border": f"1px solid {T.colors.border}",
        "box_shadow": T.shadows.shadow_2,
        "padding": T.spacing.space_4,
        "padding_bottom": 0,
        "position": "relative",
        "overflow": "hidden",
        "transition": T.motion.dur,
    }

    # Add hover effects for interactive cards
    if card_variant == "interactive":
        card_styles.update(
            {
                "_hover": {
                    "transform": "translateY(-4px)",
                    "box_shadow": T.shadows.shadow_2,
                    "border_color": T.colors.accent,
                }
            }
        )

    # Create the card container
    return rx.box(
        rx.vstack(
            rx.vstack(
                rx.text(
                    title,
                    font_size=T.typography.fs_lg,
                    font_weight=T.typography.fw_600,
                    color=T.colors.fg,
                    text_align="center",
                ),
                rx.text(
                    subtitle,
                    font_size=T.typography.fs_sm,
                    color=T.colors.fg_muted,
                    text_align="center",
                )
                if subtitle
                else None,
                spacing="1",
            ),
            children,
            spacing="1",
            width="100%",
        ),
        style=card_styles,
        width="100%",
    )


# Example usage and demo data
def demo_bar_chart() -> rx.Component:
    """Demo bar chart with sample data."""

    sample_data = [
        {"category": "Q1", "sales": 400, "revenue": 2400},
        {"category": "Q2", "sales": 300, "revenue": 1398},
        {"category": "Q3", "sales": 600, "revenue": 9800},
        {"category": "Q4", "sales": 800, "revenue": 3908},
    ]

    # Create the chart component
    chart = bar_chart(
        data=sample_data,
        x_key="category",
        y_key="sales",
        y_keys=["sales", "revenue"],
        height=350,
        show_grid=True,
        show_legend=True,
        show_tooltip=True,
    )

    # Wrap the chart in a card
    return bar_chart_card(
        title="Quarterly Performance",
        subtitle="Sales and Revenue by Quarter",
        children=chart,
        card_variant="interactive",
    )
