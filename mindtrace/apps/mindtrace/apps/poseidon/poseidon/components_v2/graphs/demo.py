"""
Demo page for the Chart components.

This module provides examples and demonstrations of the pie chart, line chart, and bar chart components
with different configurations and use cases.
"""

import reflex as rx

from .bar_chart import bar_chart, bar_chart_card
from .line_chart import line_chart, line_chart_card
from .pie_chart import pie_chart, pie_chart_card


def pie_chart_demo_page() -> rx.Component:
    """Demo page showcasing various pie chart configurations."""

    # Sample data sets
    financial_data = [
        {"name": "Revenue", "value": 450},
        {"name": "Expenses", "value": 320},
        {"name": "Profit", "value": 180},
        {"name": "Investment", "value": 120},
    ]

    traffic_data = [
        {"name": "Desktop", "value": 45},
        {"name": "Mobile", "value": 35},
        {"name": "Tablet", "value": 20},
    ]

    sales_data = [
        {"name": "Electronics", "value": 300},
        {"name": "Clothing", "value": 250},
        {"name": "Books", "value": 180},
        {"name": "Home & Garden", "value": 150},
        {"name": "Sports", "value": 120},
    ]

    return rx.vstack(
        # Header
        rx.vstack(
            rx.heading(
                "Pie Chart Components",
                font_size="3xl",
                font_weight="bold",
                color="text_primary",
                text_align="center",
            ),
            rx.text(
                "Beautiful, responsive pie charts that follow the Poseidon design system",
                font_size="lg",
                color="text_secondary",
                text_align="center",
            ),
            spacing="md",
            padding_bottom="2xl",
        ),
        # Basic Pie Chart
        rx.vstack(
            rx.heading(
                "Basic Pie Chart",
                font_size="2xl",
                font_weight="semibold",
                color="text_primary",
            ),
            pie_chart(
                data=financial_data,
                title="Financial Overview",
                subtitle="Q4 2024 Performance",
                height=300,
                show_labels=True,
                show_legend=True,
                show_tooltip=True,
            ),
            spacing="lg",
            width="100%",
            padding="xl",
        ),
        # Doughnut Chart
        rx.vstack(
            rx.heading(
                "Doughnut Chart",
                font_size="2xl",
                font_weight="semibold",
                color="text_primary",
            ),
            pie_chart(
                data=traffic_data,
                title="Device Usage",
                subtitle="Traffic by Device Type",
                height=300,
                show_labels=False,
                show_legend=True,
                show_tooltip=True,
                inner_radius="60%",
                outer_radius="90%",
                padding_angle=5,
            ),
            spacing="lg",
            width="100%",
            padding="xl",
        ),
        # Interactive Card Chart
        rx.vstack(
            rx.heading(
                "Interactive Card Chart",
                font_size="2xl",
                font_weight="semibold",
                color="text_primary",
            ),
            pie_chart_card(
                data=sales_data,
                title="Sales Distribution",
                subtitle="Revenue by Category",
                height=350,
                show_labels=True,
                show_legend=True,
                show_tooltip=True,
                inner_radius="30%",
                padding_angle=3,
                card_variant="interactive",
            ),
            spacing="lg",
            width="100%",
            padding="xl",
        ),
        # Half Pie Chart
        rx.vstack(
            rx.heading(
                "Half Pie Chart",
                font_size="2xl",
                font_weight="semibold",
                color="text_primary",
            ),
            pie_chart(
                data=financial_data[:3],  # Use only first 3 items
                title="Top 3 Categories",
                subtitle="Leading performance indicators",
                height=300,
                show_labels=True,
                show_legend=True,
                show_tooltip=True,
                start_angle=180,
                end_angle=0,
                inner_radius="40%",
            ),
            spacing="lg",
            width="100%",
            padding="xl",
        ),
        # Grid of smaller charts
        rx.vstack(
            rx.heading(
                "Chart Grid",
                font_size="2xl",
                font_weight="semibold",
                color="text_primary",
            ),
            rx.responsive_grid(
                rx.box(
                    pie_chart_card(
                        data=traffic_data,
                        title="Mobile Traffic",
                        height=250,
                        show_labels=False,
                        show_legend=True,
                        show_tooltip=True,
                        inner_radius="50%",
                        card_variant="default",
                    ),
                ),
                rx.box(
                    pie_chart_card(
                        data=financial_data[:2],
                        title="Revenue vs Expenses",
                        height=250,
                        show_labels=True,
                        show_legend=True,
                        show_tooltip=True,
                        inner_radius="20%",
                        card_variant="default",
                    ),
                ),
                rx.box(
                    pie_chart_card(
                        data=sales_data[:3],
                        title="Top Products",
                        height=250,
                        show_labels=False,
                        show_legend=True,
                        show_tooltip=True,
                        inner_radius="60%",
                        card_variant="default",
                    ),
                ),
                columns=[1, 2, 3],
                spacing="lg",
                width="100%",
            ),
            spacing="lg",
            width="100%",
            padding="xl",
        ),
        spacing="2xl",
        width="100%",
        max_width="1200px",
        margin="0 auto",
        padding="2xl",
    )


def simple_pie_chart_example() -> rx.Component:
    """Simple example of a basic pie chart."""

    data = [
        {"name": "Category A", "value": 30},
        {"name": "Category B", "value": 25},
        {"name": "Category C", "value": 20},
        {"name": "Category D", "value": 15},
        {"name": "Category E", "value": 10},
    ]

    return pie_chart(
        data=data,
        title="Simple Example",
        subtitle="Basic pie chart with 5 categories",
        height=300,
        show_labels=True,
        show_legend=True,
        show_tooltip=True,
    )


def advanced_pie_chart_example() -> rx.Component:
    """Advanced example with custom styling and animations."""

    data = [
        {"name": "Premium", "value": 40},
        {"name": "Standard", "value": 35},
        {"name": "Basic", "value": 25},
    ]

    return pie_chart_card(
        data=data,
        title="Subscription Tiers",
        subtitle="User distribution across plans",
        height=350,
        show_labels=True,
        show_legend=True,
        show_tooltip=True,
        inner_radius="40%",
        outer_radius="85%",
        padding_angle=4,
        start_angle=90,
        end_angle=450,  # Full circle + 90 degrees
        animate=True,
        card_variant="interactive",
    )


def simple_line_chart_example() -> rx.Component:
    """Simple example of a basic line chart."""

    data = [
        {"month": "Jan", "sales": 400},
        {"month": "Feb", "sales": 300},
        {"month": "Mar", "sales": 600},
        {"month": "Apr", "sales": 800},
        {"month": "May", "sales": 500},
        {"month": "Jun", "sales": 700},
    ]

    return line_chart(
        data=data,
        x_key="month",
        y_key="sales",
        title="Monthly Sales",
        subtitle="Simple line chart example",
        height=300,
        show_grid=True,
        show_legend=False,
        show_tooltip=True,
        show_dots=True,
        smooth=False,
    )


def advanced_line_chart_example() -> rx.Component:
    """Advanced example with multiple series and custom styling."""

    data = [
        {"month": "Jan", "sales": 400, "revenue": 2400},
        {"month": "Feb", "sales": 300, "revenue": 1398},
        {"month": "Mar", "sales": 600, "revenue": 9800},
        {"month": "Apr", "sales": 800, "revenue": 3908},
        {"month": "May", "sales": 500, "revenue": 4800},
        {"month": "Jun", "sales": 700, "revenue": 3800},
    ]

    return line_chart_card(
        data=data,
        x_key="month",
        y_key="sales",
        y_keys=["sales", "revenue"],
        series_key=None,
        title="Sales vs Revenue Trends",
        subtitle="Multi-series line chart with smooth curves",
        height=350,
        show_grid=True,
        show_legend=True,
        show_tooltip=True,
        show_dots=True,
        smooth=True,
        card_variant="interactive",
    )


def simple_bar_chart_example() -> rx.Component:
    """Simple example of a basic bar chart."""

    data = [
        {"category": "Feature A", "value": 400},
        {"category": "Feature B", "value": 300},
        {"category": "Feature C", "value": 600},
        {"category": "Feature D", "value": 800},
        {"category": "Feature E", "value": 500},
    ]

    return bar_chart(
        data=data,
        x_key="category",
        y_key="value",
        title="Feature Usage",
        subtitle="Simple bar chart example",
        height=300,
        show_grid=True,
        show_legend=False,
        show_tooltip=True,
    )


def defect_trends_example() -> rx.Component:
    """Defect trends example showing defects per day."""

    data = [
        {"day": "Mon", "defects": 12, "resolved": 8},
        {"day": "Tue", "defects": 15, "resolved": 10},
        {"day": "Wed", "defects": 8, "resolved": 12},
        {"day": "Thu", "defects": 20, "resolved": 15},
        {"day": "Fri", "defects": 18, "resolved": 14},
        {"day": "Sat", "defects": 5, "resolved": 6},
        {"day": "Sun", "defects": 3, "resolved": 4},
    ]

    return bar_chart_card(
        title="Defect Trends",
        subtitle="Defects found vs resolved per day",
        children=bar_chart(
            data=data,
            x_key="day",
            y_key="defects",
            y_keys=["defects", "resolved"],
            height=350,
            show_grid=True,
            show_legend=True,
            show_tooltip=True,
        ),
        card_variant="interactive",
    )


def advanced_bar_chart_example() -> rx.Component:
    """Advanced example with vertical layout and custom styling."""

    data = [
        {"team": "Frontend", "bugs": 25, "features": 45, "improvements": 30},
        {"team": "Backend", "bugs": 15, "features": 35, "improvements": 25},
        {"team": "DevOps", "bugs": 8, "features": 20, "improvements": 15},
        {"team": "QA", "bugs": 12, "features": 15, "improvements": 20},
        {"team": "Design", "bugs": 5, "features": 30, "improvements": 25},
    ]

    return bar_chart_card(
        title="Team Performance",
        subtitle="Work items by team and type",
        children=bar_chart(
            data=data,
            x_key="team",
            y_key="bugs",
            y_keys=["bugs", "features", "improvements"],
            height=350,
            show_grid=True,
            show_legend=True,
            show_tooltip=True,
            layout="horizontal",
            bar_gap=8,
            bar_category_gap="15%",
        ),
        card_variant="interactive",
    )
