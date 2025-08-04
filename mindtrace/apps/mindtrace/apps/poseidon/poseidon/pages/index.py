"""
Enhanced animated home page component.

Provides a modern welcome page with:
- Animated welcome header with gradient backgrounds
- Staggered card animations
- Smooth hover effects and transitions
- Loading animations
- Responsive design with beautiful gradients
"""

import reflex as rx
from poseidon.components import sidebar, app_header, navigation_action_card, page_header, page_container, card_grid
from poseidon.state.auth import AuthState


def animated_hero_section() -> rx.Component:
    """Hero section with animated title and clean background."""
    return rx.box(
        rx.vstack(
            # Animated main title
            rx.heading(
                "Welcome to Poseidon Toolkit",
                size="9",
                weight="bold",
                # Remove background and background_clip
                color=rx.cond(
                    AuthState.is_authenticated,
                    "#1e293b",  # slate-900
                    "white"
                ),
                text_align="center",
                margin_bottom="1rem",
                animation="fadeInUp 1s ease-out",
            ),
            # Animated subtitle
            rx.text(
                "Your industrial AI platform for intelligent automation",
                size="5",
                color=rx.cond(
                    AuthState.is_authenticated,
                    "#334155",  # slate-700
                    "#e0e7ef"
                ),
                text_align="center",
                max_width="600px",
                line_height="1.6",
                animation="fadeInUp 1s ease-out 0.2s both",
            ),
            # Animated decorative element
            rx.box(
                width="100px",
                height="4px",
                background=rx.cond(
                    AuthState.is_authenticated,
                    "linear-gradient(90deg, #2563eb, #60a5fa)",
                    "linear-gradient(90deg, #60a5fa, #1e40af)"
                ),
                border_radius="2px",
                margin_top="2rem",
                animation="scaleIn 0.8s ease-out 0.4s both",
            ),
            spacing="4",
            align="center",
        ),
        padding="4rem 2rem",
        text_align="center",
        background="transparent",
        box_shadow="none",
    )


def animated_card_wrapper(card_content: rx.Component, delay: float = 0) -> rx.Component:
    """Wrapper for cards with staggered animations."""
    return rx.box(
        card_content,
        animation=f"slideInUp 0.6s ease-out {delay}s both",
        _hover={
            "transform": "translateY(-8px)",
            "box_shadow": "0 20px 40px rgba(37, 99, 235, 0.15)",  # blue-600 shadow
            "background": "#e0e7ef",  # blue-50
        },
        transition="all 0.3s ease",
        background=rx.cond(
            AuthState.is_authenticated,
            "white",
            "rgba(255,255,255,0.08)"
        ),
        border_radius="16px",
    )


def loading_spinner() -> rx.Component:
    """Beautiful loading spinner."""
    return rx.box(
        rx.box(
            width="40px",
            height="40px",
            border="4px solid #f3f3f3",
            border_top="4px solid #667eea",
            border_radius="50%",
            animation="spin 1s linear infinite",
        ),
        display="flex",
        justify_content="center",
        align_items="center",
        height="200px",
    )


def authenticated_content() -> rx.Component:
    """Content for authenticated users with animations."""
    return rx.vstack(
        # Animated welcome message
        rx.box(
            rx.text(
                f"Hello, {AuthState.current_username}! 👋",
                size="6",
                weight="medium",
                color=rx.color("slate", 12),
                animation="fadeIn 0.8s ease-out 0.6s both",
            ),
            margin_bottom="3rem",
            text_align="center",
        ),
        # Animated cards grid
        rx.box(
            card_grid(
                animated_card_wrapper(
                    rx.link(
                        navigation_action_card(
                            title="Profile",
                            description="View and manage your account settings",
                            icon="👤",
                        ),
                        href="/profile",
                        text_decoration="none",
                    ),
                    delay=0.8,
                ),
                animated_card_wrapper(
                    rx.link(
                        navigation_action_card(
                            title="Camera Configurator",
                            description="Configure and manage your camera systems",
                            icon="📷",
                        ),
                        href="/camera-configurator",
                        text_decoration="none",
                    ),
                    delay=1.0,
                ),
                animated_card_wrapper(
                    rx.link(
                        navigation_action_card(
                            title="Image Gallery",
                            description="Browse and manage captured images",
                            icon="🖼️",
                        ),
                        href="/images",
                        text_decoration="none",
                    ),
                    delay=1.2,
                ),
                rx.cond(
                    AuthState.is_super_admin,
                    animated_card_wrapper(
                        rx.link(
                            navigation_action_card(
                                title="Super Admin",
                                description="System-wide management and configuration",
                                icon="🔧",
                            ),
                            href="/super-admin-dashboard",
                            text_decoration="none",
                        ),
                        delay=1.4,
                    ),
                    rx.cond(
                        AuthState.is_admin,
                        animated_card_wrapper(
                            rx.link(
                                navigation_action_card(
                                    title="Admin Panel",
                                    description="Organization administration and user management",
                                    icon="⚙️",
                                ),
                                href="/admin",
                                text_decoration="none",
                            ),
                            delay=1.4,
                        ),
                    ),
                ),
                min_card_width="280px",
                max_width="900px",
                justify_content="center",
            ),
            animation="fadeIn 0.8s ease-out 0.7s both",
        ),
        spacing="6",
        align="center",
        width="100%",
    )


def unauthenticated_content() -> rx.Component:
    """Content for unauthenticated users with animations."""
    return rx.vstack(
        # Animated call to action
        rx.box(
            rx.text(
                "Please sign in to access your workspace",
                color=rx.color("slate", 11),
                size="4",
                animation="fadeIn 0.8s ease-out 0.6s both",
            ),
            margin_bottom="3rem",
            text_align="center",
        ),
        # Animated auth cards
        rx.box(
            card_grid(
                animated_card_wrapper(
                    rx.link(
                        navigation_action_card(
                            title="Sign In",
                            description="Access your account and workspace",
                            icon="🔑",
                        ),
                        href="/login",
                        text_decoration="none",
                    ),
                    delay=0.8,
                ),
                animated_card_wrapper(
                    rx.link(
                        navigation_action_card(
                            title="Register",
                            description="Create a new account to get started",
                            icon="📝",
                        ),
                        href="/register",
                        text_decoration="none",
                    ),
                    delay=1.0,
                ),
                min_card_width="280px",
                max_width="700px",
                justify_content="center",
            ),
            animation="fadeIn 0.8s ease-out 0.7s both",
        ),
        spacing="6",
        align="center",
        width="100%",
    )


def index() -> rx.Component:
    """
    Enhanced animated home page with modern styling and smooth animations.
    """
    return rx.box(
        # Add CSS animations
        rx.html(
            """
            <style>
                @keyframes fadeInUp {
                    from {
                        opacity: 0;
                        transform: translateY(30px);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0);
                    }
                }
                
                @keyframes slideInUp {
                    from {
                        opacity: 0;
                        transform: translateY(40px);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0);
                    }
                }
                
                @keyframes fadeIn {
                    from {
                        opacity: 0;
                    }
                    to {
                        opacity: 1;
                    }
                }
                
                @keyframes scaleIn {
                    from {
                        opacity: 0;
                        transform: scale(0.8);
                    }
                    to {
                        opacity: 1;
                        transform: scale(1);
                    }
                }
                
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
                
                @keyframes gradient {
                    0% { background-position: 0% 50%; }
                    50% { background-position: 100% 50%; }
                    100% { background-position: 0% 50%; }
                }
            </style>
            """
        ),
        # Conditional sidebar - only show for authenticated users
        rx.cond(
            AuthState.is_authenticated,
            rx.box(
                sidebar(),
                position="fixed",
                left="0",
                top="0",
                width="240px",
                height="100vh",
                z_index="1000",
            ),
        ),
        # Conditional header - only show for authenticated users
        rx.cond(
            AuthState.is_authenticated,
            rx.box(
                app_header(),
                position="fixed",
                top="0",
                left="240px",
                right="0",
                height="60px",
                z_index="999",
            ),
        ),
        # Main content area with animated gradient background
        rx.box(
            # Animated hero section
            animated_hero_section(),
            # Content based on authentication status
            rx.cond(
                AuthState.is_authenticated,
                authenticated_content(),
                unauthenticated_content(),
            ),
            # Styling with animated gradient background
            margin_left=rx.cond(AuthState.is_authenticated, "16rem", "0"),
            margin_top=rx.cond(AuthState.is_authenticated, "60px", "0"),
            padding="2rem",
            min_height="100vh",
            background=rx.cond(
                AuthState.is_authenticated,
                "white",
                "linear-gradient(-45deg, #2563eb, #60a5fa, #1e40af, #60a5fa)"
            ),
            background_size="400% 400%",
            animation="gradient 15s ease infinite",
            display="flex",
            flex_direction="column",
            align_items="center",
            justify_content="center",
            position="relative",
            overflow="hidden",
            # Add subtle pattern overlay
            _before={
                "content": '""',
                "position": "absolute",
                "top": "0",
                "left": "0",
                "right": "0",
                "bottom": "0",
                "background": "url('data:image/svg+xml,<svg width=\"60\" height=\"60\" viewBox=\"0 0 60 60\" xmlns=\"http://www.w3.org/2000/svg\"><g fill=\"none\" fill-rule=\"evenodd\"><g fill=\"%232563eb\" fill-opacity=\"0.05\"><circle cx=\"30\" cy=\"30\" r=\"2\"/></g></g></svg>')",
                "pointer_events": "none",
            },
        ),
        # Overall container
        width="100%",
        height="100vh",
        position="relative",
        # Initialize auth check
        on_mount=AuthState.check_auth,
    ) 