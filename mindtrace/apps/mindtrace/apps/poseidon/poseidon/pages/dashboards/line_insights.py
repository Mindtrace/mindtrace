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
from poseidon.components_v2.graphs.pie_chart import pie_chart
from poseidon.components_v2.containers.chart_card import chart_card
from poseidon.components_v2.core.button import button
from poseidon.components_v2.forms.select_input import select_input
from poseidon.components_v2.core.metric_card import metric_card
from poseidon.styles.global_styles import THEME as T


def date_range_selector() -> rx.Component:
    """Date range selector component using modern select input."""
    date_options = [
        {"id": "last_7_days", "name": "Last 7 Days"},
        {"id": "last_30_days", "name": "Last 30 Days"},
        {"id": "last_90_days", "name": "Last 90 Days"},
    ]
    
    return rx.hstack(
        select_input(
            placeholder="Select date range",
            value=LineInsightsState.date_range,
            on_change=LineInsightsState.set_date_range,
            items=date_options,
            size="medium",
        ),
        button(
            "Refresh",
            on_click=LineInsightsState.load_dashboard_data,
            variant="ghost",
            size="2",
            loading=LineInsightsState.loading,
        ),
        spacing="3",
        align="center",
        width="300px",
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
    """Defect rate over time chart showing overall trend."""
    chart = line_chart(
        data=LineInsightsState.defect_rate_data,
        x_key="date",
        y_key="defect_rate",
        height=350,  # Full height without filter
        show_grid=True,
        show_legend=True,
        show_tooltip=True,
        smooth=True,
    )
    
    chart_content = rx.cond(
        LineInsightsState.loading_defect_chart,
        rx.center(
            rx.spinner(size="3"),
            height="350px",
        ),
        chart,
    )
    
    return chart_card(
        title="Defect Rate Over Time",
        subtitle="Percentage of parts with defects",
        children=chart_content,
    )


def frequent_defects_chart() -> rx.Component:
    """Most frequent defects pie chart - no filter needed as it shows distribution."""
    chart = pie_chart(
        data=LineInsightsState.frequent_defects_data,
        data_key="count",
        name_key="defect_type",
        height=350,  # Full height since no filter
        show_labels=True,
        show_legend=True,
        show_tooltip=True,
        inner_radius="30%",  # Creates a doughnut chart
        outer_radius="80%",
    )
    
    chart_content = rx.cond(
        LineInsightsState.loading_frequent_chart,
        rx.center(
            rx.spinner(size="3"),
            height="350px",
        ),
        chart,
    )
    
    return chart_card(
        title="Most Frequent Defects",
        subtitle="Distribution of defect types in selected time range",
        children=chart_content,
    )


def camera_defect_matrix_chart() -> rx.Component:
    """Camera defect matrix chart - shows distribution across cameras, no filter needed."""  
    chart = bar_chart(
        data=LineInsightsState.camera_defect_matrix_data,
        x_key="camera",
        y_keys=LineInsightsState.camera_chart_defect_types,
        height=400,
        show_grid=True,
        show_legend=True,
        show_tooltip=True,
        layout="horizontal",
        bar_size=30,
        bar_gap=4,
        bar_category_gap="20%",
    )
    
    chart_content = rx.cond(
        LineInsightsState.loading_matrix_chart,
        rx.center(
            rx.spinner(size="3"),
            height="350px",
        ),
        chart,
    )
    
    return chart_card(
        title="Defect Distribution by Camera", 
        subtitle="Defect counts per camera position in selected time range",
        children=chart_content,
    )


def weld_defect_rate_chart() -> rx.Component:
    """Weld defect rate chart showing defect percentage per weld inspection point."""
    chart = bar_chart(
        data=LineInsightsState.weld_defect_rate_data,
        x_key="weld_id",
        y_key="defect_rate", 
        height=350,
        show_grid=True,
        show_legend=False,
        show_tooltip=True,
        layout="horizontal",  # Changed to horizontal like camera chart
        bar_size=20,
        bar_gap=1,
        bar_category_gap="5%",
    )
    
    chart_content = rx.cond(
        LineInsightsState.loading_weld_chart,
        rx.center(
            rx.spinner(size="3"),
            height="350px",
        ),
        chart,
    )
    
    return chart_card(
        title="Defect Rate by Weld ID",
        subtitle="Percentage of defective inspections per weld point (0% means all healthy)",
        children=chart_content,
    )


def healthy_vs_defective_chart() -> rx.Component:
    """Healthy vs defective classification distribution pie chart."""
    chart = pie_chart(
        data=LineInsightsState.healthy_vs_defective_data,
        data_key="count",
        name_key="status",
        height=350,
        show_labels=True,
        show_legend=True,
        show_tooltip=True,
        inner_radius="40%",  # Creates a doughnut chart
        outer_radius="80%",
    )
    
    chart_content = rx.cond(
        LineInsightsState.loading_healthy_vs_defective_chart,
        rx.center(
            rx.spinner(size="3"),
            height="350px",
        ),
        chart,
    )
    
    return chart_card(
        title="Classification Distribution",
        subtitle="Overall healthy vs defective classification breakdown",
        children=chart_content,
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
                    f"{LineInsightsState.plant_id} - {LineInsightsState.project_name}",  # Dynamic project name
                    font_size=T.typography.fs_lg,
                    color=T.colors.fg,
                    font_weight=T.typography.fw_500,
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
                "Defective Parts",
                f"{LineInsightsState.total_defects_found:,}",
                "Parts with defects",
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
        
        # Second row: Weld defect rate and classification distribution
        rx.grid(
            healthy_vs_defective_chart(),
            weld_defect_rate_chart(),
            columns="2",
            spacing="4",
            width="100%",
        ),
        
        # Third row: Frequent defects and camera matrix
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
            
            rx.divider(color=T.colors.border),
            line_insights_content(),
            
            # Error messages only
            rx.cond(
                LineInsightsState.error,
                rx.callout(
                    LineInsightsState.error,
                    icon="triangle-alert",
                    color_scheme="red",
                ),
                rx.fragment(),
            ),
            
            spacing="6",
            width="100%",
            padding_y=T.spacing.space_6,
        ),
        on_mount=LineInsightsState.on_mount,
    )