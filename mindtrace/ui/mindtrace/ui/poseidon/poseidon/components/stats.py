"""Poseidon Stats Components - Buridan UI Styling.

Renamed Buridan UI pantry stats for Poseidon use cases
while keeping the exact styling patterns.
"""

import reflex as rx
from poseidon.state.auth import AuthState
from poseidon.state.user_management import UserManagementState


def admin_dashboard_stats():
    """Admin dashboard stats - keeps Buridan UI styling."""
    
    def stat_item(name: str, value: str):
        return rx.box(
            rx.text(name, class_name="text-gray-500 font-light"),
            rx.text(
                value,
                class_name="order-first text-2xl font-semibold tracking-tight sm:text-3xl",
            ),
            class_name="mx-auto flex max-w-xs flex-col gap-y-4",
        )
    
    return rx.box(
        rx.box(
            stat_item("Total Users", UserManagementState.total_users_count or "0"),
            stat_item("Active Users", UserManagementState.active_users_count or "0"),
            stat_item("Organizations", "1"),  # Could be dynamic if needed
            class_name="grid grid-cols-1 gap-x-8 gap-y-16 text-center lg:grid-cols-3",
        ),
        class_name="mx-auto max-w-7xl px-6 lg:px-8",
    )


def user_profile_stats(user_data: dict = None):
    """User profile stats - modern, clean styling."""
    
    def stat_item(name: str, value: str, color: str = "blue"):
        return rx.box(
            rx.vstack(
            rx.text(
                value,
                    size="6",
                    weight="bold",
                    color=rx.color(color, 11),
                    text_align="center",
                ),
                rx.text(
                    name,
                    size="2",
                    color=rx.color("slate", 11),
                    text_align="center",
                    weight="medium",
            ),
                spacing="1",
                align="center",
            ),
            padding="1.5rem",
            border_radius="8px",
            background=rx.color("slate", 2),
            border=f"1px solid {rx.color('slate', 6)}",
            min_width="120px",
            text_align="center",
        )
    
    return rx.hstack(
        stat_item("Organization Roles", AuthState.user_org_roles.length(), "blue"),
        stat_item("Project Assignments", AuthState.user_project_assignments.length(), "orange"),
        stat_item("Account Status", rx.cond(AuthState.is_authenticated, "Active", "Inactive"), "green"),
        spacing="4",
        justify="center",
        flex_wrap="wrap",
        width="100%",
    )


def system_overview_stats(stats_data: list = None):
    """System overview stats - keeps Buridan UI styling."""
    
    # Default stats if none provided
    if not stats_data:
        stats_data = [
            {"name": "System Uptime", "value": "99.9%"},
            {"name": "Data Processed", "value": "2.4 TB"},
            {"name": "API Requests", "value": "1.2M"},
        ]
    
    def stat_item(stat: dict):
        return rx.box(
            rx.text(stat["name"], class_name="text-gray-500 font-light"),
            rx.text(
                stat["value"],
                class_name="order-first text-2xl font-semibold tracking-tight sm:text-3xl",
            ),
            class_name="mx-auto flex max-w-xs flex-col gap-y-4",
        )
    
    return rx.box(
        rx.box(
            rx.foreach(stats_data, stat_item),
            class_name="grid grid-cols-1 gap-x-8 gap-y-16 text-center lg:grid-cols-3",
        ),
        class_name="mx-auto max-w-7xl px-6 lg:px-8",
    )


def custom_stats_grid(stats_list: list):
    """Custom stats grid - keeps Buridan UI styling."""
    
    def stat_item(stat: dict):
        return rx.box(
            rx.text(stat.get("name", ""), class_name="text-gray-500 font-light"),
            rx.text(
                stat.get("value", ""),
                class_name="order-first text-2xl font-semibold tracking-tight sm:text-3xl",
            ),
            class_name="mx-auto flex max-w-xs flex-col gap-y-4",
        )
    
    # Determine grid columns based on number of stats
    col_class = "grid-cols-1"
    if len(stats_list) == 2:
        col_class = "lg:grid-cols-2"
    elif len(stats_list) >= 3:
        col_class = "lg:grid-cols-3"
    
    return rx.box(
        rx.box(
            rx.foreach(stats_list, stat_item),
            class_name=f"grid {col_class} gap-x-8 gap-y-16 text-center",
        ),
        class_name="mx-auto max-w-7xl px-6 lg:px-8",
    )


# Keep original demo stats for reference
def stat_v1():
    """Original Buridan UI demo stats - for reference."""
    demo_stats = [
        {"id": 1, "name": "Transactions every 24 hours", "value": "44 million"},
        {"id": 2, "name": "Assets under holding", "value": "$119 trillion"},
        {"id": 3, "name": "New users annually", "value": "46,000"},
    ]
    
    return rx.box(
        rx.box(
            rx.foreach(
                demo_stats,
                lambda stat: rx.box(
                    rx.text(stat["name"], class_name="text-gray-500 font-light"),
                    rx.text(
                        stat["value"],
                        class_name="order-first text-2xl font-semibold tracking-tight sm:text-3xl",
                    ),
                    class_name="mx-auto flex max-w-xs flex-col gap-y-4",
                ),
            ),
            class_name="grid grid-cols-1 gap-x-8 gap-y-16 text-center lg:grid-cols-3",
        ),
        class_name="mx-auto max-w-7xl px-6 lg:px-8",
    )
