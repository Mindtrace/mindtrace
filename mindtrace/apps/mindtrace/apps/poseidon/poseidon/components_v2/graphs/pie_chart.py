"""
Pie Chart Component for Poseidon

A beautiful, responsive pie chart component that follows the app's design system.
Supports both simple and advanced configurations with custom styling.
"""

from typing import Any, Dict, List, Optional, Union

import reflex as rx

from poseidon.styles.global_styles import THEME as T
from poseidon.components_v2.containers import chart_card

# Poseidon Color Palette for Pie Charts
CHART_COLORS = [
    "#4C78A8",
    "#F58518",
    "#E45756",
    "#72B7B2",
    "#54A24B",
    "#EECA3B",
    "#B279A2",
    "#FF9DA6",
    "#9D755D",
    "#BAB0AC",
]


def get_chart_colors(count: int) -> List[str]:
    """Get a list of colors for the chart based on the number of data points."""
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


def get_chart_colors_for_data(data: List[Dict[str, Any]]) -> List[str]:
    """Get a list of colors for the chart based on the data."""
    # Use a fixed number of colors for Reflex Vars
    return CHART_COLORS[:12]  # Return first 12 colors


def pie_chart(
    data: List[Dict[str, Any]],
    data_key: str = "value",
    name_key: str = "name",
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    width: Union[str, int] = "100%",
    height: Union[str, int] = 300,
    show_labels: bool = True,
    show_legend: bool = True,
    show_tooltip: bool = True,
    inner_radius: Union[str, int] = "0%",
    outer_radius: Union[str, int] = "80%",
    padding_angle: int = 2,
    start_angle: int = 0,
    end_angle: int = 360,
    animate: bool = True,
    **kwargs,
) -> rx.Component:
    """
    Create a beautiful pie chart component.

    Args:
        data: List of dictionaries containing the data
        data_key: Key for the numerical values
        name_key: Key for the category names
        title: Chart title
        subtitle: Chart subtitle
        width: Chart width
        height: Chart height
        show_labels: Whether to show labels on pie slices
        show_legend: Whether to show legend
        show_tooltip: Whether to show tooltip on hover
        inner_radius: Inner radius for doughnut chart (use "0%" for full pie)
        outer_radius: Outer radius of the chart
        padding_angle: Space between pie slices
        start_angle: Starting angle in degrees
        end_angle: Ending angle in degrees
        animate: Whether to animate the chart
        **kwargs: Additional props for the chart

    Returns:
        A Reflex component containing the pie chart
    """

    # Create pie chart components
    chart_components = []

    # Create cell components for colors (always create 12 cells for Reflex Vars)
    cell_components = []
    for i, color in enumerate(CHART_COLORS[:12]):
        cell_components.append(
            rx.recharts.cell(
                key=f"cell-{i}",
                fill=color,
            )
        )

    # Add the main pie component with cells as children
    pie_component = rx.recharts.pie(
        data=data,
        data_key=data_key,
        name_key=name_key,
        cx="50%",
        cy="50%",
        inner_radius=inner_radius,
        outer_radius=outer_radius,
        padding_angle=padding_angle,
        start_angle=start_angle,
        end_angle=end_angle,
        fill=CHART_COLORS[0],
        stroke=T.colors.bg,
        stroke_width=2,
        *cell_components,
    )

    chart_components.append(pie_component)

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
                vertical_align="bottom",
                height=36,
                icon_type="circle",
                wrapper_style={
                    "padding": T.spacing.space_4,
                    "padding_bottom": 0,
                    "font_family": T.typography.font_sans,
                    "font_size": T.typography.fs_sm,
                    "color": T.colors.fg_muted,
                },
            )
        )

    # Create the chart container
    chart_container = rx.recharts.pie_chart(
        *chart_components,
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


def pie_chart_card(
    title: str,
    subtitle: Optional[str] = None,
    children: Optional[rx.Component] = None,
    card_variant: str = "default",
) -> rx.Component:
    """
    Create a pie chart wrapped in a beautiful card container.

    Args:
        title: Card title
        subtitle: Card subtitle
        children: The component to be wrapped in the card (e.g., a chart)
        card_variant: Card styling variant

    Returns:
        A Reflex component containing the children in a card
    """
    return chart_card(
        title=title,
        subtitle=subtitle,
        children=children,
        card_variant=card_variant,
    )


# Example usage and demo data
def demo_pie_chart() -> rx.Component:
    """Demo pie chart with sample data."""

    sample_data = [
        {"name": "Revenue", "value": 400},
        {"name": "Expenses", "value": 300},
        {"name": "Profit", "value": 200},
        {"name": "Investment", "value": 100},
    ]

    # Create the chart component
    chart = pie_chart(
        data=sample_data,
        data_key="value",
        name_key="name",
        height=350,
        show_labels=True,
        show_legend=True,
        show_tooltip=True,
        inner_radius="30%",
    )

    # Wrap the chart in a card
    return pie_chart_card(
        title="Financial Overview",
        subtitle="Q4 2024 Performance",
        children=chart,
        card_variant="interactive",
    )


def demo_doughnut_chart() -> rx.Component:
    """Demo doughnut chart with sample data."""

    sample_data = [
        {"name": "Desktop", "value": 45},
        {"name": "Mobile", "value": 35},
        {"name": "Tablet", "value": 20},
    ]

    # Create the chart component
    chart = pie_chart(
        data=sample_data,
        data_key="value",
        name_key="name",
        height=300,
        show_labels=False,
        show_legend=True,
        show_tooltip=True,
        inner_radius="60%",
        outer_radius="90%",
        padding_angle=5,
    )

    # Wrap the chart in a card
    return pie_chart_card(
        title="Device Usage",
        subtitle="Traffic by Device Type",
        children=chart,
        card_variant="default",
    )
