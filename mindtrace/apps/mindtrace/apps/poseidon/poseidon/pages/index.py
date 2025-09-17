import reflex as rx
from poseidon.components import (
    page_header,
    page_container,
    card_grid,
    navigation_action_card,
)
from poseidon.state.auth import AuthState


def index() -> rx.Component:
    """Authenticated dashboard home."""
    return page_container(
        # Header
        page_header(
            title="Dashboard",
            description=rx.cond(
                AuthState.current_first_name,
                f"Welcome back, {AuthState.current_first_name} {AuthState.current_last_name}",
                "Welcome back"
            ),
        ),

        # Quick nav tiles
        card_grid(
            rx.link(
                navigation_action_card(
                    title="Profile",
                    description="Manage your account settings",
                    icon="👤",
                ),
                href="/profile",
                text_decoration="none",
            ),
            rx.link(
                navigation_action_card(
                    title="Camera Configurator",
                    description="Configure and manage camera systems",
                    icon="📷",
                ),
                href="/camera-configurator",
                text_decoration="none",
            ),
            rx.link(
                navigation_action_card(
                    title="Image Viewer",
                    description="Browse and review captured images",
                    icon="🖼️",
                ),
                href="/image-viewer",  # <-- align with your routes
                text_decoration="none",
            ),
            rx.link(
                navigation_action_card(
                    title="Line Insights",
                    description="See KPIs and trends for your lines",
                    icon="📈",
                ),
                # You likely navigate with real plant/line ids elsewhere; keep as placeholder or route builder
                href="/plants/placeholder/lines/placeholder/line-insights",
                text_decoration="none",
            ),
            rx.cond(
                AuthState.is_super_admin,
                rx.link(
                    navigation_action_card(
                        title="Super Admin",
                        description="System-wide configuration and monitoring",
                        icon="🔧",
                    ),
                    href="/super-admin-dashboard",
                    text_decoration="none",
                ),
            ),
            rx.cond(
                AuthState.is_admin,
                rx.link(
                    navigation_action_card(
                        title="Admin Panel",
                        description="Organization & user administration",
                        icon="⚙️",
                    ),
                    href="/admin",
                    text_decoration="none",
                ),
            ),
            min_card_width="260px",
            max_width="1100px",
        ),

        # (Optional) secondary section: add quick stats / recent activity later
        # rx.box(
        #     rx.heading("Recent Activity", size="4", margin_bottom="0.5rem"),
        #     rx.text("No activity yet.", color=rx.color("slate", 11)),
        #     width="100%",
        #     max_width="1100px",
        #     margin_top="2rem",
        # ),

        width="100%",
    )
