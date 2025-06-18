"""Main dashboard page component.

Provides the landing page experience with:
- Welcome message and platform description
- Feature preview and coming soon content
- Call-to-action buttons with consistent styling
- Responsive design using design system
"""

import reflex as rx
from reflex_app.components.navbar import navbar
from reflex_app.styles import COLORS, TYPOGRAPHY, CSS_SPACING, SIZING, SPACING, button_variants, BOX_SHADOWS


def index() -> rx.Component:
    """Main dashboard page with welcome content.
    
    Returns:
        Complete landing page with navbar and centered content
    """
    return rx.vstack(
        navbar(active="/"),
        rx.center(
            rx.box(
                rx.vstack(
                    rx.heading(
                        "Welcome to MindTrace", 
                        font_size=TYPOGRAPHY["font_sizes"]["4xl"],
                        color=COLORS["primary"],
                        text_align="center",
                    ),
                    rx.text(
                        "Your intelligent data viewer and management platform",
                        color=COLORS["text_muted"],
                        font_size=TYPOGRAPHY["font_sizes"]["xl"],
                        text_align="center",
                        max_width=SIZING["max_width_content"],
                    ),
                    rx.box(
                        rx.vstack(
                            rx.heading(
                                "Coming Soon: Data Viewer", 
                                font_size=TYPOGRAPHY["font_sizes"]["2xl"],
                                color=COLORS["text"],
                            ),
                            rx.text(
                                "• Browse and visualize your data with interactive grids",
                                color=COLORS["text"],
                            ),
                            rx.text(
                                "• View detailed information in modal dialogs",
                                color=COLORS["text"],
                            ),
                            rx.text(
                                "• Navigate large datasets with smart pagination",
                                color=COLORS["text"],
                            ),
                            rx.text(
                                "• Secure authentication and user management",
                                color=COLORS["text"],
                            ),
                            spacing=SPACING["sm"],
                            align="start",
                        ),
                        padding=CSS_SPACING["xl"],
                        background=COLORS["surface"],
                        border_radius=SIZING["border_radius"],
                        border=f"{SIZING['border_width']} solid {COLORS['border']}",
                    ),
                    rx.hstack(
                        rx.button(
                            "🚀 Get Started", 
                            **button_variants["primary"]
                        ),
                        rx.button(
                            "📖 Learn More", 
                            **button_variants["secondary"]
                        ),
                        spacing=SPACING["md"],
                    ),
                    spacing=SPACING["lg"],
                    align="center",
                    max_width=SIZING["max_width_content"],
                ),
                padding=CSS_SPACING["2xl"],
                background=COLORS["surface"],
                border=f"{SIZING['border_width']} solid {COLORS['border']}",
                border_radius=SIZING["border_radius"],
                box_shadow=BOX_SHADOWS["lg"],
            ),
        ),
        spacing=SPACING["lg"],
        background=COLORS["background"],
        min_height=SIZING["full_height"],
    ) 