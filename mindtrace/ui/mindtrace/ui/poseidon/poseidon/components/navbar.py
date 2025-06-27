"""Modern sidebar navigation component.

Provides a professional dashboard sidebar with:
- Organized navigation sections
- Role-based access control for features
- Modern styling with hover effects
- User profile section at top
- Consistent with template design
"""

import reflex as rx
from poseidon.styles.styles import (
    COLORS, TYPOGRAPHY, SIZING, SPACING, 
    sidebar_variants, header_variants
)
from poseidon.state.auth import AuthState

def sidebar() -> rx.Component:
    """Modern sidebar navigation for dashboard.
    
    Returns:
        Fixed sidebar with organized navigation sections
    """
    
    def nav_section(title: str, items: list) -> rx.Component:
        """Create a navigation section with title and items."""
        return rx.box(
            rx.text(
                title,
                **sidebar_variants["section_title"]
            ),
            rx.vstack(
                *items,
                spacing="1",
                align="stretch",
            ),
            **sidebar_variants["section"]
        )
    
    def nav_item(text: str, href: str, icon: str = "") -> rx.Component:
        """Create a styled navigation item."""
        # Check if this is the current page (simplified)
        is_active = False  # We'll implement proper active state later
        
        return rx.link(
            rx.hstack(
                rx.text(icon, margin_right=SPACING["sm"]) if icon else rx.fragment(),
                rx.text(text),
                spacing="2",
                align="center",
            ),
            href=href,
            style=sidebar_variants["nav_item_active"] if is_active else sidebar_variants["nav_item"]
        )
    
    # Navigation sections based on template
    navigation_sections = [
        ("NAVIGATION", [
            nav_item("Dashboard", "/", "📊"),
            nav_item("Image Gallery", "/images", "🖼️"),
        ]),
        ("DATA & ANALYTICS", [
            nav_item("Data Management Hub", "/data", "📁"),
            nav_item("Device & Integration Hub", "/devices", "🔌"),
            nav_item("Model Development Center", "/models", "🤖"),
        ]),
        ("OPERATIONS", [
            nav_item("Deployment & Operations", "/deploy", "🚀"),
            nav_item("Monitoring & Analytics", "/monitoring", "📈"),
            nav_item("Alert & Notification Center", "/alerts", "🔔"),
        ]),
        ("TOOLS", [
            nav_item("Workflow Sandbox", "/workflow", "⚙️"),
        ]),
    ]
    
    # Add admin section if user is admin
    admin_section = ("ADMIN", [
        nav_item("Admin & Security", "/admin", "🔐"),
    ])
    
    return rx.cond(
        AuthState.is_authenticated,
        rx.box(
            # Logo/Brand section
            rx.box(
                rx.text(
                    "Poseidon Toolkit",
                    font_size=TYPOGRAPHY["font_sizes"]["xl"],
                    font_weight=TYPOGRAPHY["font_weights"]["bold"],
                    color=COLORS["text"],
                    margin_bottom=SPACING["lg"],
                ),
                padding_bottom=SPACING["lg"],
                border_bottom=f"{SIZING['border_width']} solid {COLORS['border']}",
                margin_bottom=SPACING["lg"],
            ),
            
            # Navigation sections for authenticated users
            rx.vstack(
                # User profile section
                nav_section("USER", [
                    nav_item("Profile", "/profile", "👤"),
                ]),
                
                # Main navigation
                nav_section("NAVIGATION", [
                    nav_item("Dashboard", "/", "📊"),
                    nav_item("Image Gallery", "/images", "🖼️"),
                ]),
                
                # Admin section (conditional)
                rx.cond(
                    AuthState.is_admin,
                    nav_section("ADMIN", [
                        nav_item("Admin Panel", "/admin", "⚙️"),
                    ]),
                ),
                
                spacing="4",
                align="stretch",
            ),
            
            **sidebar_variants["container"]
        ),
        # Empty sidebar for non-authenticated users
        rx.box(
            **sidebar_variants["container"]
        )
    )

def header() -> rx.Component:
    """Modern header with search and user profile.
    
    Returns:
        Fixed header component
    """
    return rx.box(
        # Search section
        rx.input(
            placeholder="Search datasets, models, devices...",
            **header_variants["search"]
        ),
        
        # User profile section
        rx.cond(
            AuthState.is_authenticated,
            rx.box(
                rx.hstack(
                    rx.text(
                        AuthState.user_display_name,
                        font_weight=TYPOGRAPHY["font_weights"]["medium"],
                        color=COLORS["text"],
                    ),
                    rx.text(
                        AuthState.role_display,
                        font_size=TYPOGRAPHY["font_sizes"]["sm"],
                        color=COLORS["text_muted"],
                    ),
                    rx.link(
                        "Profile",
                        href="/profile",
                        color=COLORS["primary"],
                        font_weight=TYPOGRAPHY["font_weights"]["medium"],
                        font_size=TYPOGRAPHY["font_sizes"]["sm"],
                    ),
                    rx.button(
                        "Logout",
                        on_click=AuthState.logout,
                        size="2",
                        variant="ghost",
                    ),
                    spacing="3",
                    align="center",
                ),
                **header_variants["user_profile"]
            ),
            # Not authenticated - show login link
            rx.link(
                "Login",
                href="/login",
                color=COLORS["primary"],
                font_weight=TYPOGRAPHY["font_weights"]["medium"],
            ),
        ),
        
        **header_variants["container"],
        on_mount=AuthState.check_auth,
    )

def navbar(active: str = "") -> rx.Component:
    """Legacy navbar function for compatibility.
    
    Args:
        active: Current active route (unused in new design)
        
    Returns:
        Empty fragment (sidebar and header are now separate)
    """
    # Return empty fragment since we now use sidebar + header layout
    return rx.fragment() 