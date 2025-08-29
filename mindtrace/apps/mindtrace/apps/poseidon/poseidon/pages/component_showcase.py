"""Component Showcase Page - Demonstrates all components_v2 components."""

import reflex as rx

from poseidon.components_v2.branding import logo_poseidon
from poseidon.components_v2.containers import (
    card, 
    login_page_container,
    horizontal_tabs,
    vertical_tabs,
    pill_tabs,
    underline_tabs,
    card_tabs,
)
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
                # Tabs Section
                card(
                    [
                        rx.vstack(
                            rx.heading("Tabs Container", size="4", color=T.colors.fg),
                            rx.text(
                                "Modern tab interfaces with multiple variants and orientations",
                                size="2",
                                color=T.colors.fg_muted,
                            ),
                            # Default Horizontal Tabs
                            rx.vstack(
                                rx.heading("Default Horizontal Tabs", size="3", color=T.colors.fg),
                                horizontal_tabs([
                                    {
                                        "label": "Overview",
                                        "value": "overview",
                                        "icon": "📊",
                                        "content": rx.vstack(
                                            rx.text("Welcome to the Overview tab!", size="4", color=T.colors.fg),
                                            rx.text("This is the default horizontal tabs variant with smooth animations and modern styling.", size="3", color=T.colors.fg_muted),
                                            rx.hstack(
                                                button("Action 1", variant="primary", size="sm"),
                                                button("Action 2", variant="secondary", size="sm"),
                                                spacing="3",
                                            ),
                                            spacing="4",
                                            align_items="start",
                                        ),
                                    },
                                    {
                                        "label": "Analytics",
                                        "value": "analytics",
                                        "icon": "📈",
                                        "content": rx.vstack(
                                            rx.text("Analytics Dashboard", size="4", color=T.colors.fg),
                                            rx.text("View your data insights and performance metrics here.", size="3", color=T.colors.fg_muted),
                                            rx.box(
                                                rx.text("📊 Sample Chart", size="2", color=T.colors.fg_muted),
                                                background=T.colors.surface_2,
                                                padding=T.spacing.space_4,
                                                border_radius=T.radius.r_md,
                                                border=f"1px solid {T.colors.border}",
                                                width="100%",
                                                height="120px",
                                                display="flex",
                                                align_items="center",
                                                justify_content="center",
                                            ),
                                            spacing="4",
                                            align_items="start",
                                        ),
                                    },
                                    {
                                        "label": "Settings",
                                        "value": "settings",
                                        "icon": "⚙️",
                                        "content": rx.vstack(
                                            rx.text("Settings Panel", size="4", color=T.colors.fg),
                                            rx.text("Configure your preferences and account settings.", size="3", color=T.colors.fg_muted),
                                            rx.vstack(
                                                rx.text("🔔 Notifications: Enabled", size="3", color=T.colors.fg),
                                                rx.text("🌙 Dark Mode: Disabled", size="3", color=T.colors.fg),
                                                rx.text("🔒 Privacy: Standard", size="3", color=T.colors.fg),
                                                spacing="2",
                                                align_items="start",
                                            ),
                                            spacing="4",
                                            align_items="start",
                                        ),
                                    },
                                ]),
                                spacing="4",
                                align_items="start",
                                width="100%",
                            ),
                            # Pill Tabs
                            rx.vstack(
                                rx.heading("Pill Tabs", size="3", color=T.colors.fg),
                                pill_tabs([
                                    {
                                        "label": "Active",
                                        "value": "active",
                                        "content": rx.vstack(
                                            rx.text("Active Projects", size="4", color=T.colors.fg),
                                            rx.text("Currently running projects and tasks.", size="3", color=T.colors.fg_muted),
                                            rx.hstack(
                                                rx.box(
                                                    rx.text("Project A", size="2", color="white"),
                                                    background=T.colors.success,
                                                    padding=T.spacing.space_2,
                                                    border_radius=T.radius.r_sm,
                                                ),
                                                rx.box(
                                                    rx.text("Project B", size="2", color="white"),
                                                    background=T.colors.info,
                                                    padding=T.spacing.space_2,
                                                    border_radius=T.radius.r_sm,
                                                ),
                                                spacing="2",
                                            ),
                                            spacing="4",
                                            align_items="start",
                                        ),
                                    },
                                    {
                                        "label": "Completed",
                                        "value": "completed",
                                        "content": rx.vstack(
                                            rx.text("Completed Projects", size="4", color=T.colors.fg),
                                            rx.text("Successfully finished projects.", size="3", color=T.colors.fg_muted),
                                            rx.text("🎉 All tasks completed successfully!", size="3", color=T.colors.success),
                                            spacing="4",
                                            align_items="start",
                                        ),
                                    },
                                    {
                                        "label": "Archived",
                                        "value": "archived",
                                        "content": rx.vstack(
                                            rx.text("Archived Projects", size="4", color=T.colors.fg),
                                            rx.text("Old projects moved to archive.", size="3", color=T.colors.fg_muted),
                                            rx.text("📦 15 projects archived", size="3", color=T.colors.fg_muted),
                                            spacing="4",
                                            align_items="start",
                                        ),
                                    },
                                ]),
                                spacing="4",
                                align_items="start",
                                width="100%",
                            ),
                            # Underline Tabs
                            rx.vstack(
                                rx.heading("Underline Tabs", size="3", color=T.colors.fg),
                                underline_tabs([
                                    {
                                        "label": "Profile",
                                        "value": "profile",
                                        "content": rx.vstack(
                                            rx.text("User Profile", size="4", color=T.colors.fg),
                                            rx.text("Manage your personal information and preferences.", size="3", color=T.colors.fg_muted),
                                            rx.hstack(
                                                rx.box(
                                                    rx.text("👤", size="4"),
                                                    background=T.colors.surface_2,
                                                    padding=T.spacing.space_4,
                                                    border_radius=T.radius.r_full,
                                                    border=f"1px solid {T.colors.border}",
                                                ),
                                                rx.vstack(
                                                    rx.text("John Doe", size="3", weight="bold", color=T.colors.fg),
                                                    rx.text("john.doe@example.com", size="2", color=T.colors.fg_muted),
                                                    spacing="1",
                                                    align_items="start",
                                                ),
                                                spacing="4",
                                                align_items="center",
                                            ),
                                            spacing="4",
                                            align_items="start",
                                        ),
                                    },
                                    {
                                        "label": "Security",
                                        "value": "security",
                                        "content": rx.vstack(
                                            rx.text("Security Settings", size="4", color=T.colors.fg),
                                            rx.text("Manage your account security and privacy.", size="3", color=T.colors.fg_muted),
                                            rx.vstack(
                                                rx.text("🔐 Two-Factor Authentication: Enabled", size="3", color=T.colors.fg),
                                                rx.text("🔑 Last Password Change: 30 days ago", size="3", color=T.colors.fg),
                                                rx.text("📱 Trusted Devices: 3", size="3", color=T.colors.fg),
                                                spacing="2",
                                                align_items="start",
                                            ),
                                            spacing="4",
                                            align_items="start",
                                        ),
                                    },
                                    {
                                        "label": "Billing",
                                        "value": "billing",
                                        "content": rx.vstack(
                                            rx.text("Billing Information", size="4", color=T.colors.fg),
                                            rx.text("Manage your subscription and payment methods.", size="3", color=T.colors.fg_muted),
                                            rx.box(
                                                rx.vstack(
                                                    rx.text("💳 Current Plan: Pro", size="3", color=T.colors.fg),
                                                    rx.text("💰 Next Billing: March 15, 2024", size="3", color=T.colors.fg),
                                                    rx.text("📊 Usage: 75% of monthly limit", size="3", color=T.colors.fg),
                                                    spacing="2",
                                                    align_items="start",
                                                ),
                                                background=T.colors.surface_2,
                                                padding=T.spacing.space_4,
                                                border_radius=T.radius.r_md,
                                                border=f"1px solid {T.colors.border}",
                                            ),
                                            spacing="4",
                                            align_items="start",
                                        ),
                                    },
                                ]),
                                spacing="4",
                                align_items="start",
                                width="100%",
                            ),
                            # Card Tabs
                            rx.vstack(
                                rx.heading("Card Tabs", size="3", color=T.colors.fg),
                                card_tabs([
                                    {
                                        "label": "Dashboard",
                                        "value": "dashboard",
                                        "icon": "🏠",
                                        "content": rx.vstack(
                                            rx.text("Main Dashboard", size="4", color=T.colors.fg),
                                            rx.text("Your central hub for all activities and metrics.", size="3", color=T.colors.fg_muted),
                                            rx.hstack(
                                                rx.box(
                                                    rx.vstack(
                                                        rx.text("📈", size="3"),
                                                        rx.text("Revenue", size="2", weight="bold", color=T.colors.fg),
                                                        rx.text("$12,450", size="2", color=T.colors.success),
                                                        spacing="1",
                                                        align_items="center",
                                                    ),
                                                    background=T.colors.surface_2,
                                                    padding=T.spacing.space_4,
                                                    border_radius=T.radius.r_md,
                                                    border=f"1px solid {T.colors.border}",
                                                    flex="1",
                                                ),
                                                rx.box(
                                                    rx.vstack(
                                                        rx.text("👥", size="3"),
                                                        rx.text("Users", size="2", weight="bold", color=T.colors.fg),
                                                        rx.text("1,234", size="2", color=T.colors.info),
                                                        spacing="1",
                                                        align_items="center",
                                                    ),
                                                    background=T.colors.surface_2,
                                                    padding=T.spacing.space_4,
                                                    border_radius=T.radius.r_md,
                                                    border=f"1px solid {T.colors.border}",
                                                    flex="1",
                                                ),
                                                spacing="4",
                                                width="100%",
                                            ),
                                            spacing="4",
                                            align_items="start",
                                        ),
                                    },
                                    {
                                        "label": "Reports",
                                        "value": "reports",
                                        "icon": "📋",
                                        "content": rx.vstack(
                                            rx.text("Reports & Analytics", size="4", color=T.colors.fg),
                                            rx.text("Generate and view detailed reports.", size="3", color=T.colors.fg_muted),
                                            rx.box(
                                                rx.text("📊 Generating monthly report...", size="3", color=T.colors.fg_muted),
                                                background=T.colors.surface_2,
                                                padding=T.spacing.space_4,
                                                border_radius=T.radius.r_md,
                                                border=f"1px solid {T.colors.border}",
                                                width="100%",
                                                height="100px",
                                                display="flex",
                                                align_items="center",
                                                justify_content="center",
                                            ),
                                            spacing="4",
                                            align_items="start",
                                        ),
                                    },
                                    {
                                        "label": "Team",
                                        "value": "team",
                                        "icon": "👥",
                                        "content": rx.vstack(
                                            rx.text("Team Management", size="4", color=T.colors.fg),
                                            rx.text("Manage your team members and permissions.", size="3", color=T.colors.fg_muted),
                                            rx.vstack(
                                                rx.hstack(
                                                    rx.text("👤 Alice Johnson", size="3", color=T.colors.fg),
                                                    rx.text("Admin", size="2", color=T.colors.success),
                                                    spacing="4",
                                                    justify_content="space_between",
                                                    width="100%",
                                                ),
                                                rx.hstack(
                                                    rx.text("👤 Bob Smith", size="3", color=T.colors.fg),
                                                    rx.text("Editor", size="2", color=T.colors.info),
                                                    spacing="4",
                                                    justify_content="space_between",
                                                    width="100%",
                                                ),
                                                rx.hstack(
                                                    rx.text("👤 Carol Davis", size="3", color=T.colors.fg),
                                                    rx.text("Viewer", size="2", color=T.colors.fg_muted),
                                                    spacing="4",
                                                    justify_content="space_between",
                                                    width="100%",
                                                ),
                                                spacing="2",
                                                align_items="start",
                                                width="100%",
                                            ),
                                            spacing="4",
                                            align_items="start",
                                        ),
                                    },
                                ]),
                                spacing="4",
                                align_items="start",
                                width="100%",
                            ),
                            # Vertical Tabs
                            rx.vstack(
                                rx.heading("Vertical Tabs", size="3", color=T.colors.fg),
                                rx.hstack(
                                    vertical_tabs([
                                        {
                                            "label": "General",
                                            "value": "general",
                                            "icon": "⚙️",
                                            "content": rx.vstack(
                                                rx.text("General Settings", size="4", color=T.colors.fg),
                                                rx.text("Basic application settings and preferences.", size="3", color=T.colors.fg_muted),
                                                rx.vstack(
                                                    rx.text("🌍 Language: English", size="3", color=T.colors.fg),
                                                    rx.text("🕐 Timezone: UTC", size="3", color=T.colors.fg),
                                                    rx.text("📱 Theme: Light", size="3", color=T.colors.fg),
                                                    spacing="2",
                                                    align_items="start",
                                                ),
                                                spacing="4",
                                                align_items="start",
                                            ),
                                        },
                                        {
                                            "label": "Notifications",
                                            "value": "notifications",
                                            "icon": "🔔",
                                            "content": rx.vstack(
                                                rx.text("Notification Preferences", size="4", color=T.colors.fg),
                                                rx.text("Configure how you receive notifications.", size="3", color=T.colors.fg_muted),
                                                rx.vstack(
                                                    rx.text("📧 Email: Enabled", size="3", color=T.colors.fg),
                                                    rx.text("📱 Push: Enabled", size="3", color=T.colors.fg),
                                                    rx.text("🔔 Sound: Disabled", size="3", color=T.colors.fg),
                                                    spacing="2",
                                                    align_items="start",
                                                ),
                                                spacing="4",
                                                align_items="start",
                                            ),
                                        },
                                        {
                                            "label": "Privacy",
                                            "value": "privacy",
                                            "icon": "🔒",
                                            "content": rx.vstack(
                                                rx.text("Privacy Settings", size="4", color=T.colors.fg),
                                                rx.text("Manage your privacy and data settings.", size="3", color=T.colors.fg_muted),
                                                rx.vstack(
                                                    rx.text("📊 Analytics: Enabled", size="3", color=T.colors.fg),
                                                    rx.text("🍪 Cookies: Required only", size="3", color=T.colors.fg),
                                                    rx.text("📱 Location: Disabled", size="3", color=T.colors.fg),
                                                    spacing="2",
                                                    align_items="start",
                                                ),
                                                spacing="4",
                                                align_items="start",
                                            ),
                                        },
                                    ]),
                                    spacing="6",
                                    align_items="start",
                                    width="100%",
                                ),
                                spacing="4",
                                align_items="start",
                                width="100%",
                            ),
                            # Bottom Centered Tabs
                            rx.vstack(
                                rx.heading("Bottom Centered Tabs", size="3", color=T.colors.fg),
                                rx.box(
                                    rx.tabs.root(
                                        rx.vstack(
                                            # Content area that changes based on selected tab
                                            rx.tabs.content(
                                                rx.vstack(
                                                    rx.heading("🏠 Home Dashboard", size="4", color=T.colors.fg),
                                                    rx.text("Welcome to your home dashboard! Here you can see an overview of your activities.", size="3", color=T.colors.fg_muted),
                                                    rx.box(
                                                        rx.vstack(
                                                            rx.text("📊 Recent Activity", size="3", color=T.colors.fg, font_weight="600"),
                                                            rx.text("• 3 new messages", size="2", color=T.colors.fg_muted),
                                                            rx.text("• 2 pending tasks", size="2", color=T.colors.fg_muted),
                                                            rx.text("• 1 system update", size="2", color=T.colors.fg_muted),
                                                            spacing="2",
                                                            align_items="start",
                                                        ),
                                                        background=T.colors.surface_2,
                                                        padding=T.spacing.space_4,
                                                        border_radius=T.radius.r_md,
                                                        border=f"1px solid {T.colors.border}",
                                                        width="100%",
                                                    ),
                                                    spacing="4",
                                                    align_items="start",
                                                ),
                                                value="home",
                                            ),
                                            rx.tabs.content(
                                                rx.vstack(
                                                    rx.heading("🔍 Search Results", size="4", color=T.colors.fg),
                                                    rx.text("Search through your data and files.", size="3", color=T.colors.fg_muted),
                                                    rx.box(
                                                        rx.vstack(
                                                            rx.text("🔎 Quick Search", size="3", color=T.colors.fg, font_weight="600"),
                                                            rx.text("• Documents (12 results)", size="2", color=T.colors.fg_muted),
                                                            rx.text("• Images (5 results)", size="2", color=T.colors.fg_muted),
                                                            rx.text("• Videos (3 results)", size="2", color=T.colors.fg_muted),
                                                            spacing="2",
                                                            align_items="start",
                                                        ),
                                                        background=T.colors.surface_2,
                                                        padding=T.spacing.space_4,
                                                        border_radius=T.radius.r_md,
                                                        border=f"1px solid {T.colors.border}",
                                                        width="100%",
                                                    ),
                                                    spacing="4",
                                                    align_items="start",
                                                ),
                                                value="search",
                                            ),
                                            rx.tabs.content(
                                                rx.vstack(
                                                    rx.heading("👤 User Profile", size="4", color=T.colors.fg),
                                                    rx.text("Manage your personal information and preferences.", size="3", color=T.colors.fg_muted),
                                                    rx.box(
                                                        rx.vstack(
                                                            rx.text("👤 Profile Info", size="3", color=T.colors.fg, font_weight="600"),
                                                            rx.text("• Name: John Doe", size="2", color=T.colors.fg_muted),
                                                            rx.text("• Email: john@example.com", size="2", color=T.colors.fg_muted),
                                                            rx.text("• Member since: Jan 2024", size="2", color=T.colors.fg_muted),
                                                            spacing="2",
                                                            align_items="start",
                                                        ),
                                                        background=T.colors.surface_2,
                                                        padding=T.spacing.space_4,
                                                        border_radius=T.radius.r_md,
                                                        border=f"1px solid {T.colors.border}",
                                                        width="100%",
                                                    ),
                                                    spacing="4",
                                                    align_items="start",
                                                ),
                                                value="profile",
                                            ),
                                            rx.tabs.content(
                                                rx.vstack(
                                                    rx.heading("⚙️ Settings", size="4", color=T.colors.fg),
                                                    rx.text("Configure your application settings and preferences.", size="3", color=T.colors.fg_muted),
                                                    rx.box(
                                                        rx.vstack(
                                                            rx.text("⚙️ App Settings", size="3", color=T.colors.fg, font_weight="600"),
                                                            rx.text("• Theme: Light Mode", size="2", color=T.colors.fg_muted),
                                                            rx.text("• Language: English", size="2", color=T.colors.fg_muted),
                                                            rx.text("• Notifications: Enabled", size="2", color=T.colors.fg_muted),
                                                            spacing="2",
                                                            align_items="start",
                                                        ),
                                                        background=T.colors.surface_2,
                                                        padding=T.spacing.space_4,
                                                        border_radius=T.radius.r_md,
                                                        border=f"1px solid {T.colors.border}",
                                                        width="100%",
                                                    ),
                                                    spacing="4",
                                                    align_items="start",
                                                ),
                                                value="settings",
                                            ),
                                            spacing="4",
                                            align_items="start",
                                            width="100%",
                                            flex="1",
                                        ),
                                        # Bottom centered tabs
                                        rx.center(
                                            rx.tabs.list(
                                                rx.tabs.trigger("🏠 Home", value="home", style={"cursor": "pointer"}),
                                                rx.tabs.trigger("🔍 Search", value="search", style={"cursor": "pointer"}),
                                                rx.tabs.trigger("👤 Profile", value="profile", style={"cursor": "pointer"}),
                                                rx.tabs.trigger("⚙️ Settings", value="settings", style={"cursor": "pointer"}),
                                                style={
                                                    "background": T.colors.surface_2,
                                                    "border_radius": T.radius.r_lg,
                                                    "padding": T.spacing.space_2,
                                                    "border": f"1px solid {T.colors.border}",
                                                }
                                            ),
                                            width="100%",
                                            padding_top=T.spacing.space_6,
                                        ),
                                        spacing="6",
                                        align_items="start",
                                        width="100%",
                                        height="400px",
                                        default_value="home",
                                    ),
                                    background=T.colors.surface,
                                    border_radius=T.radius.r_xl,
                                    border=f"1px solid {T.colors.border}",
                                    padding=T.spacing.space_6,
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
