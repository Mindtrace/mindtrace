"""Simple home page component.

Provides a clean welcome page with:
- Welcome header
- Simple navigation options
- Clean modern styling
"""

import reflex as rx
from poseidon.components.navbar import sidebar, header
from poseidon.styles.styles import (
    COLORS, TYPOGRAPHY, SIZING, SPACING,
    card_variants, content_variants
)
from poseidon.state.auth import AuthState


def simple_nav_card(title: str, description: str, icon: str, link: str) -> rx.Component:
    """Create a simple navigation card.
    
    Args:
        title: Card title
        description: Card description
        icon: Emoji icon
        link: Navigation link
        
    Returns:
        Simple styled navigation card
    """
    return rx.link(
        rx.box(
            rx.vstack(
                rx.text(
                    icon,
                    font_size=TYPOGRAPHY["font_sizes"]["3xl"],
                    margin_bottom=SPACING["sm"],
                ),
                rx.heading(
                    title,
                    font_size=TYPOGRAPHY["font_sizes"]["lg"],
                    font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                    color=COLORS["text"],
                    margin_bottom=SPACING["xs"],
                ),
                rx.text(
                    description,
                    color=COLORS["text_muted"],
                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                    text_align="center",
                ),
                spacing="2",
                align="center",
            ),
            **card_variants["feature"],
        ),
        href=link,
        text_decoration="none",
    )


def index() -> rx.Component:
    """Simple home page with clean layout.
    
    Returns:
        Clean home page with basic navigation
    """
    return rx.fragment(
        # Sidebar navigation
        sidebar(),
        
        # Header
        header(),
        
        # Main content area
        rx.box(
            # Welcome section
            rx.box(
                rx.heading(
                    "Welcome to Poseidon Toolkit",
                    **content_variants["page_title"]
                ),
                rx.text(
                    "Your industrial AI platform for intelligent automation",
                    **content_variants["page_subtitle"]
                ),
                **content_variants["page_header"]
            ),
            
            # Simple navigation cards for authenticated users
            rx.cond(
                AuthState.is_authenticated,
                rx.vstack(
                    rx.text(
                        f"Hello, {AuthState.current_username}!",
                        font_size=TYPOGRAPHY["font_sizes"]["lg"],
                        color=COLORS["text"],
                        font_weight=TYPOGRAPHY["font_weights"]["medium"],
                        margin_bottom=SPACING["lg"],
                    ),
                    rx.box(
                        simple_nav_card(
                            "Profile",
                            "View and manage your account",
                            "👤",
                            "/profile"
                        ),
                        rx.cond(
                            AuthState.is_admin,
                            simple_nav_card(
                                "Admin Panel",
                                "System administration",
                                "⚙️",
                                "/admin"
                            ),
                        ),
                        display="grid",
                        grid_template_columns="repeat(auto-fit, minmax(250px, 1fr))",
                        gap=SPACING["lg"],
                        max_width="600px",
                    ),
                    spacing="6",
                    align="center",
                ),
                # For non-authenticated users
                rx.vstack(
                    rx.text(
                        "Please sign in to access your workspace",
                        color=COLORS["text_muted"],
                        font_size=TYPOGRAPHY["font_sizes"]["lg"],
                        margin_bottom=SPACING["lg"],
                    ),
                    rx.box(
                        simple_nav_card(
                            "Sign In",
                            "Access your account",
                            "🔑",
                            "/login"
                        ),
                        simple_nav_card(
                            "Register",
                            "Create new account",
                            "📝",
                            "/register"
                        ),
                        display="grid",
                        grid_template_columns="repeat(auto-fit, minmax(250px, 1fr))",
                        gap=SPACING["lg"],
                        max_width="600px",
                    ),
                    spacing="6",
                    align="center",
                ),
            ),
            
            **content_variants["container"]
        ),
        
        # Initialize auth check
        on_mount=AuthState.check_auth,
    ) 