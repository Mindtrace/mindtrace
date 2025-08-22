"""
Line Insights Dashboard Page

Dynamic dashboard showing production line metrics and analytics.
Uses chart components to visualize parts scanned, defect rates, and more.
"""

import reflex as rx
from typing import Optional
from poseidon.state.line_insights import LineInsightsState
from poseidon.components_v2.containers.page_container import page_container
from poseidon.components_v2.graphs.line_chart import line_chart
from poseidon.components_v2.graphs.bar_chart import bar_chart
from poseidon.components_v2.containers.chart_card import chart_card
from poseidon.components_v2.core.button import button
# from poseidon.components_v2.forms.select_input import select_input
from poseidon.styles.global_styles import THEME as T


def metric_card(title: str, value: str, subtitle: Optional[str] = None) -> rx.Component:
    """Create a metric card for displaying key metrics."""
    return rx.card(
        rx.vstack(
            rx.text(
                title,
                font_size=T.typography.fs_sm,
                color=T.colors.fg_muted,
                font_weight=T.typography.fw_500,
            ),
            rx.text(
                value,
                font_size=T.typography.fs_3xl,
                font_weight=T.typography.fw_700,
                color=T.colors.fg,
            ),
            rx.cond(
                subtitle,
                rx.text(
                    subtitle,
                    font_size=T.typography.fs_sm,
                    color=T.colors.fg_subtle,
                ),
                rx.fragment(),
            ),
            spacing="2",
            align="start",
        ),
        padding=T.spacing.space_4,
        background=T.colors.surface,
        border=f"1px solid {T.colors.border}",
        border_radius=T.radius.r_lg,
        box_shadow=T.shadows.shadow_1,
        width="100%",
    )


def date_range_selector() -> rx.Component:
    """Date range selector component."""
    return rx.hstack(
        rx.select(
            ["last_7_days", "last_30_days", "last_90_days"],
            value=LineInsightsState.date_range,
            on_change=LineInsightsState.set_date_range,
            placeholder="Select date range",
            width="200px",
        ),
        button(
            "Refresh",
            on_click=LineInsightsState.load_dashboard_data,
            variant="ghost",
            size="sm",
            loading=LineInsightsState.loading,
        ),
        spacing="3",
        align="center",
    )


def parts_scanned_chart() -> rx.Component:
    """Parts scanned over time chart."""
    chart = line_chart(
        data=LineInsightsState.parts_scanned_data,
        x_key="date",
        y_keys=["count", "defects"],
        height=350,
        show_grid=True,
        show_legend=True,
        show_tooltip=True,
        smooth=True,
    )
    
    return chart_card(
        title="Parts Scanned Over Time",
        subtitle="Daily scan counts and defect detection",
        children=rx.cond(
            LineInsightsState.loading_parts_chart,
            rx.center(
                rx.spinner(size="3"),
                height="350px",
            ),
            chart,
        ),
    )


def defect_rate_chart() -> rx.Component:
    """Defect rate over time chart."""
    chart = line_chart(
        data=LineInsightsState.defect_rate_data,
        x_key="date",
        y_key="defect_rate",  # Use y_key instead of y_keys for single series
        height=350,
        show_grid=True,
        show_legend=True,
        show_tooltip=True,
        smooth=True,
    )
    
    return chart_card(
        title="Defect Rate Over Time",
        subtitle="Percentage of parts with defects",
        children=rx.cond(
            LineInsightsState.loading_defect_chart,
            rx.center(
                rx.spinner(size="3"),
                height="350px",
            ),
            chart,
        ),
    )


def frequent_defects_chart() -> rx.Component:
    """Most frequent defects bar chart."""
    chart = bar_chart(
        data=LineInsightsState.frequent_defects_data,
        x_key="defect_type",
        y_key="count",
        height=350,
        show_grid=True,
        show_legend=False,
        show_tooltip=True,
        layout="horizontal",  # Changed to horizontal for better defect type readability
    )
    
    return chart_card(
        title="Most Frequent Defects",
        subtitle="Top 10 defect types by occurrence",
        children=rx.cond(
            LineInsightsState.loading_frequent_chart,
            rx.center(
                rx.spinner(size="3"),
                height="350px",
            ),
            chart,
        ),
    )


def camera_defect_matrix_chart() -> rx.Component:
    """Camera defect matrix chart."""
    # Create chart with predefined defect types for now
    # In a real implementation, this would be dynamically generated
    chart = bar_chart(
        data=LineInsightsState.camera_defect_matrix_data,
        x_key="camera",
        y_keys=["Surface Scratch", "Color Mismatch", "Dimension Error", "Missing Component"],
        height=350,
        show_grid=True,
        show_legend=True,
        show_tooltip=True,
        layout="horizontal",  # Changed to horizontal for better readability
    )
    
    return chart_card(
        title="Defect Distribution by Camera",
        subtitle="Defect counts per camera position",
        children=rx.cond(
            LineInsightsState.loading_matrix_chart,
            rx.center(
                rx.spinner(size="3"),
                height="350px",
            ),
            chart,
        ),
    )


def line_insights_header() -> rx.Component:
    """Header section with title and metrics."""
    return rx.vstack(
        # Title and controls
        rx.hstack(
            rx.vstack(
                rx.heading(
                    "Line Insights",
                    size="8",
                    font_weight=T.typography.fw_700,
                    color=T.colors.fg,
                ),
                rx.text(
                    LineInsightsState.formatted_date_range,
                    font_size=T.typography.fs_sm,
                    color=T.colors.fg_muted,
                ),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            date_range_selector(),
            width="100%",
            align="center",
        ),
        
        # Metrics cards
        rx.grid(
            metric_card(
                "Total Parts Scanned",
                f"{LineInsightsState.total_parts_scanned:,}",
                "Parts processed",
            ),
            metric_card(
                "Total Defects Found",
                f"{LineInsightsState.total_defects_found:,}",
                "Defects detected",
            ),
            metric_card(
                "Average Defect Rate",
                f"{LineInsightsState.average_defect_rate:.1f}%",
                "Overall defect percentage",
            ),
            metric_card(
                "Active Cameras",
                f"{LineInsightsState.active_cameras}",
                "Currently operational",
            ),
            columns="4",
            spacing="4",
            width="100%",
        ),
        
        spacing="6",
        width="100%",
    )


def line_insights_content() -> rx.Component:
    """Main content area with charts."""
    return rx.vstack(
        # First row: Parts scanned and defect rate
        rx.grid(
            parts_scanned_chart(),
            defect_rate_chart(),
            columns="2",
            spacing="4",
            width="100%",
        ),
        
        # Second row: Frequent defects and camera matrix
        rx.grid(
            frequent_defects_chart(),
            camera_defect_matrix_chart(),
            columns="2",
            spacing="4",
            width="100%",
        ),
        
        spacing="4",
        width="100%",
    )


def line_insights_page() -> rx.Component:
    """Main Line Insights dashboard page."""
    return page_container(
        rx.vstack(
            line_insights_header(),
            
            # Sample data notice
            rx.callout(
                "📊 Displaying sample data for demonstration. Connect your production line data to see real metrics.",
                icon="info",
                color_scheme="blue",
                size="1",
            ),
            
            rx.divider(color=T.colors.border),
            line_insights_content(),
            
            # Error/Success messages
            rx.cond(
                LineInsightsState.error,
                rx.callout(
                    LineInsightsState.error,
                    icon="triangle-alert",
                    color_scheme="red",
                ),
                rx.fragment(),
            ),
            rx.cond(
                LineInsightsState.success,
                rx.callout(
                    LineInsightsState.success,
                    icon="check",
                    color_scheme="green",
                ),
                rx.fragment(),
            ),
            
            spacing="6",
            width="100%",
            padding_y=T.spacing.space_6,
        ),
        on_mount=LineInsightsState.on_mount,
    )