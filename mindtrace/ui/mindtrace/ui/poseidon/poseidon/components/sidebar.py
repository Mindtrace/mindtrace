"""Poseidon Sidebar Navigation Component.

Customized from Buridan UI with:
- Poseidon navigation structure
- Role-based access control
- Auth state integration
- Consistent with Poseidon theme
"""

import reflex as rx
from reflex.experimental import ClientStateVar
from poseidon.state.auth import AuthState

ACTIVE_ITEM = ClientStateVar.create("active_item", "")

# Poseidon Navigation Structure - Only implemented sections
POSEIDON_USER_NAV = [
    {"name": "Profile", "href": "/profile", "icon": "👤"},
    {"name": "Image Viewer", "href": "/image-viewer", "icon": "🔍"},
    {"name": "Camera Configurator", "href": "/camera-configurator", "icon": "📷"},
]

POSEIDON_ADMIN_NAV = [
    {"name": "Admin Panel", "href": "/admin", "icon": "⚙️"},
    {"name": "User Management", "href": "/user-management", "icon": "👥"},
    {"name": "Project Management", "href": "/project-management", "icon": "📋"}
]

POSEIDON_SUPER_ADMIN_NAV = [
    {"name": "System Management", "href": "/super-admin", "icon": "🔧"}
]

POSEIDON_SUPER_ADMIN_MANAGEMENT_NAV = [
    {"name": "System Dashboard", "href": "/super-admin", "icon": "🖥️"},
    {"name": "User Management", "href": "/super-admin/users", "icon": "👥"},
    {"name": "Organization Management", "href": "/organization-management", "icon": "🏢"},
    {"name": "Project Management", "href": "/project-management", "icon": "📋"},
]


def create_divider():
    """Create a consistent divider."""
    return rx.divider(
        border_bottom=f"0.81px solid {rx.color('gray', 4)}", 
        bg="transparent"
    )


def create_sidebar_menu_items(routes: list[dict]):
    """Create menu items from Poseidon routes."""

    def item(data):
        item_name = data["name"]
        item_href = data.get("href", "#")
        item_icon = data.get("icon", "")
        
        return rx.hstack(
            rx.link(
                rx.hstack(
                    rx.cond(
                        item_icon,
                        rx.text(item_icon, margin_right="8px"),
                        rx.fragment(),
                    ),
                    rx.text(
                        item_name,
                        _hover={"color": rx.color("slate", 12)},
                        color=rx.cond(
                            ACTIVE_ITEM.value == item_name,
                            rx.color("slate", 12),
                            rx.color("slate", 11),
                        ),
                        size="2",
                        font_weight=rx.cond(
                            ACTIVE_ITEM.value == item_name, "semibold", "normal"
                        ),
                    ),
                    spacing="2",
                    align="center",
                ),
                href=item_href,
                text_decoration="none",
                on_click=ACTIVE_ITEM.set_value(item_name),
                width="100%",
                padding_left="10px",
            ),
            spacing="0",
            align_items="center",
            width="100%",
            border_left=rx.cond(
                ACTIVE_ITEM.value == item_name,
                f"1px solid {rx.color('blue', 10)}",
                f"0.81px solid {rx.color('gray', 4)}",
            ),
            height="32px",
        )

    return rx.vstack(rx.foreach(routes, item), spacing="0", width="100%")


def side_bar_wrapper(title: str, component: rx.Component):
    """Create a sidebar section."""
    return rx.vstack(
        rx.text(title, size="1", color=rx.color("slate", 12), weight="bold"),
        component,
        padding="1em",
    )


def sidebar():
    """Main Poseidon sidebar with role-based navigation - only implemented sections."""
    
    # Only render sidebar for authenticated users
    return rx.scroll_area(
            rx.box(
                ACTIVE_ITEM,
                
                # Logo/Brand section
                rx.box(
                    rx.hstack(
                        rx.image(
                            src="/mindtrace-logo.png",
                            alt="MindTrace Logo",
                            width="100px",
                            height="32px",
                            margin_right="0.5rem",
                        ),
                        rx.text(
                            "Poseidon",
                            size="4",
                            weight="bold",
                            text_align="center",
                            color=rx.color("slate", 12),
                            margin_bottom="4",
                        ),
                        align="center",
                        spacing="2",
                    ),
                    padding="1em",
                    border_bottom=f"0.81px solid {rx.color('gray', 4)}",
                ),
                
                # User section
                side_bar_wrapper("USER", create_sidebar_menu_items(POSEIDON_USER_NAV)),
                create_divider(),
                
                # Admin section (conditional)
                rx.cond(
                    AuthState.is_admin,
                    rx.fragment(
                        side_bar_wrapper("ADMIN", create_sidebar_menu_items(POSEIDON_ADMIN_NAV)),
                        create_divider(),
                    )
                ),
                
                # Super Admin section (conditional)
                rx.cond(
                    AuthState.is_super_admin,
                    rx.fragment(
                        side_bar_wrapper("SUPER ADMIN", create_sidebar_menu_items([
                            {"name": "User Management", "href": "/user-management", "icon": "👥"},
                            {"name": "Organization Management", "href": "/organization-management", "icon": "🏢"},
                            {"name": "Project Management", "href": "/project-management", "icon": "📋"}
                        ])),
                        create_divider(),
                    )
                ),
                
                # Sidebar container styling
                background=rx.color("gray", 1),
                border_right=f"1px solid {rx.color('gray', 4)}",
                width="100%",
                height="100%",
            ),
            height="100vh",
            width="100%",
            max_width="240px",
            background=rx.color("gray", 1),
    )

# Also export for direct access
__all__ = ["sidebar", "poseidon_sidebar", "sidebar_v1"] 