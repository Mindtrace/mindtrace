"""Navigation bar component.

Provides authentication-aware navigation with:
- Dynamic link visibility based on user auth status
- Role-based access control for admin features
- Consistent styling using design system constants
- User welcome message and logout functionality
"""

import reflex as rx
from reflex_app.styles import COLORS, TYPOGRAPHY, CSS_SPACING, SIZING, SPACING, TRANSITIONS, WIDTHS
from reflex_app.state.auth import AuthState

def navbar(active: str = "") -> rx.Component:
    """Navigation bar with authentication-aware links.
    
    Args:
        active: Current active route for highlighting
        
    Returns:
        Responsive navigation component with conditional content
    """
    
    # Navigation link configurations
    public_links = [("Home", "/")]
    auth_links = [("Login", "/login"), ("Register", "/register")]
    user_links = [("Profile", "/profile")]
    admin_links = [("Admin", "/admin")]
    
    def nav_link(text: str, href: str) -> rx.Component:
        """Create a styled navigation link."""
        return rx.link(
            text,
            href=href,
            color=COLORS["primary"] if active == href else COLORS["text"],
            padding=f"{CSS_SPACING['sm']} {CSS_SPACING['md']}",
            border_radius=SIZING["border_radius"],
            transition=TRANSITIONS["normal"],
            _hover={
                "background": COLORS["surface"],
                "color": COLORS["primary"],
            },
        )
    
    return rx.box(
        rx.hstack(
            # Logo section
            rx.text(
                "MindTrace",
                font_size=TYPOGRAPHY["font_sizes"]["2xl"],
                font_weight=TYPOGRAPHY["font_weights"]["bold"],
                color=COLORS["primary"],
            ),
            rx.spacer(),
            
            # Navigation links section
            rx.hstack(
                # Public links (always visible)
                *[nav_link(text, href) for text, href in public_links],
                
                # Auth links (visible when NOT authenticated)
                rx.cond(
                    ~AuthState.is_authenticated,
                    rx.fragment(*[nav_link(text, href) for text, href in auth_links]),
                ),
                
                # User links (visible when authenticated)
                rx.cond(
                    AuthState.is_authenticated,
                    rx.fragment(*[nav_link(text, href) for text, href in user_links]),
                ),
                
                # Admin links (visible for authenticated admins only)
                rx.cond(
                    AuthState.is_authenticated & AuthState.has_role("admin"),
                    rx.fragment(*[nav_link(text, href) for text, href in admin_links]),
                ),
                
                # User info and logout (visible when authenticated)
                rx.cond(
                    AuthState.is_authenticated,
                    rx.hstack(
                        rx.vstack(
                            rx.text(
                                f"Welcome, {AuthState.current_username}!",
                                color=COLORS["text_muted"],
                                font_size=TYPOGRAPHY["font_sizes"]["sm"],
                            ),
                            rx.cond(
                                AuthState.has_project(),
                                rx.text(
                                    f"Project: {AuthState.user_project}",
                                    color=COLORS["primary"],
                                    font_size=TYPOGRAPHY["font_sizes"]["xs"],
                                ),
                            ),
                            rx.cond(
                                AuthState.has_organization(),
                                rx.text(
                                    f"Org: {AuthState.user_organization}",
                                    color=COLORS["primary"],
                                    font_size=TYPOGRAPHY["font_sizes"]["xs"],
                                ),
                            ),
                            spacing=SPACING["xs"],
                            align="end",
                        ),
                        rx.button(
                            "Logout",
                            on_click=AuthState.logout,
                            background=COLORS["transparent"],
                            color=COLORS["error"],
                            padding=f"{CSS_SPACING['sm']} {CSS_SPACING['md']}",
                            border="none",
                            _hover={"background": COLORS["surface"]},
                        ),
                        spacing=SPACING["sm"],
                    ),
                ),
                spacing=SPACING["md"],
            ),
            justify="between",
            align="center",
            width=WIDTHS["full"],
        ),
        padding=CSS_SPACING["md"],
        border_bottom=f"{SIZING['border_width']} solid {COLORS['border']}",
        background=COLORS["background"],
        on_mount=AuthState.check_auth,
    ) 