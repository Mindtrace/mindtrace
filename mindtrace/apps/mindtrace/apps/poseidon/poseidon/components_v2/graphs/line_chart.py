"""
Line Chart Component for Poseidon

A beautiful, responsive line chart component that follows the app's design system.
Supports both simple and advanced configurations with custom styling.
"""

from typing import Any, Dict, List, Optional, Union

import reflex as rx
from reflex.vars.base import Var

from poseidon.styles.global_styles import THEME as T
from poseidon.components_v2.containers import chart_card

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


def line_chart(
    data: Union[List[Dict[str, Any]], Var[List[Dict[str, Any]]]],
    x_key: str = "x",
    y_key: str = "y",
    series_key: Optional[str] = None,
    y_keys: Optional[Union[List[str], Var[List[str]]]] = None,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    width: Union[str, int] = "100%",
    height: Union[str, int] = 300,
    show_grid: bool = True,
    show_legend: bool = True,
    show_tooltip: bool = True,
    show_dots: bool = True,
    smooth: bool = False,
    animate: bool = True,
    **kwargs,
) -> rx.Component:
    """
    Create a beautiful line chart component.

    Args:
        data: List of dictionaries containing the data
        x_key: Key for the x-axis values
        y_key: Key for the y-axis values
        series_key: Key for grouping data into series (optional)
        title: Chart title
        subtitle: Chart subtitle
        width: Chart width
        height: Chart height
        show_grid: Whether to show grid lines
        show_legend: Whether to show legend
        show_tooltip: Whether to show tooltip on hover
        show_dots: Whether to show data points
        smooth: Whether to use smooth curves
        animate: Whether to animate the chart
        **kwargs: Additional props for the chart

    Returns:
        A Reflex component containing the line chart
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
    chart_components.append(
        rx.recharts.x_axis(
            data_key=x_key,
            stroke=T.colors.fg_muted,
            tick_line=False,
            axis_line=False,
            tick_margin=10,
        )
    )

    # Add y-axis
    chart_components.append(
        rx.recharts.y_axis(
            stroke=T.colors.fg_muted,
            tick_line=False,
            axis_line=False,
            tick_margin=10,
        )
    )

    # Handle single series vs multiple series
    colors = get_chart_colors(12)  # Use generous amount for dynamic cases
    
    if y_keys is not None:
        if isinstance(y_keys, Var):
            # For Var y_keys, create multiple lines with different colors
            # Since we can't use dynamic indexing, create fixed lines for each color
            for i, color in enumerate(colors[:8]):  # Limit to 8 colors
                chart_components.append(
                    rx.cond(
                        y_keys.length() > i,  # Only show if we have this many keys
                        rx.recharts.line(
                            type_="monotone",
                            data_key=y_keys[i],  # Use indexed access
                            stroke=color,
                            stroke_width=2,
                            dot=show_dots,
                            active_dot={"r": 6, "stroke": color, "stroke_width": 2, "fill": T.colors.bg},
                            name=y_keys[i],
                            smooth=smooth,
                        ),
                        rx.fragment(),  # Empty if not enough keys
                    )
                )
        else:
            # For static y_keys (list), iterate normally
            for i, key in enumerate(y_keys):
                chart_components.append(
                    rx.recharts.line(
                        type_="monotone",
                        data_key=key,
                        stroke=colors[i % len(colors)],
                        stroke_width=2,
                        dot=show_dots,
                        active_dot={"r": 6, "stroke": colors[i % len(colors)], "stroke_width": 2, "fill": T.colors.bg},
                        name=key.title(),
                        smooth=smooth,
                    )
                )
    elif series_key:
        # Multiple series - group data by series
        series_data = {}
        for item in data:
            series_name = item.get(series_key, "Default")
            if series_name not in series_data:
                series_data[series_name] = []
            series_data[series_name].append(item)

        # Create a line for each series
        colors = get_chart_colors(len(series_data))
        for i, (series_name, series_items) in enumerate(series_data.items()):
            chart_components.append(
                rx.recharts.line(
                    type_="monotone",
                    data_key=y_key,
                    stroke=colors[i],
                    stroke_width=2,
                    dot=show_dots,
                    active_dot={"r": 6, "stroke": colors[i], "stroke_width": 2, "fill": T.colors.bg},
                    name=series_name,
                    smooth=smooth,
                )
            )
    else:
        # Single series
        chart_components.append(
            rx.recharts.line(
                type_="monotone",
                data_key=y_key,
                stroke=CHART_COLORS[0],
                stroke_width=2,
                dot=show_dots,
                active_dot={"r": 6, "stroke": CHART_COLORS[0], "stroke_width": 2, "fill": T.colors.bg},
                smooth=smooth,
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
    chart_container = rx.recharts.line_chart(
        *chart_components,
        data=data,
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


def line_chart_card(
    title: str,
    subtitle: Optional[str] = None,
    children: Optional[rx.Component] = None,
    card_variant: str = "default",
) -> rx.Component:
    """
    Create a line chart wrapped in a card container.

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
def demo_line_chart() -> rx.Component:
    """Demo line chart with sample data."""

    sample_data = [
        {"month": "Jan", "sales": 400, "revenue": 2400},
        {"month": "Feb", "sales": 300, "revenue": 1398},
        {"month": "Mar", "sales": 200, "revenue": 9800},
        {"month": "Apr", "sales": 278, "revenue": 3908},
        {"month": "May", "sales": 189, "revenue": 4800},
        {"month": "Jun", "sales": 239, "revenue": 3800},
    ]

    # Create the chart component
    chart = line_chart(
        data=sample_data,
        x_key="month",
        y_key="sales",
        series_key=None,  # Single series
        height=350,
        show_grid=True,
        show_legend=True,
        show_tooltip=True,
        show_dots=True,
        smooth=True,
    )

    # Wrap the chart in a card
    return line_chart_card(
        title="Sales & Revenue Trends",
        subtitle="Monthly performance overview",
        children=chart,
        card_variant="interactive",
    )
