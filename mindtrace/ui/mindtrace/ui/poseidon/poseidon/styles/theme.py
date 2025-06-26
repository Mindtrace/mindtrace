"""Simplified theme configuration for the Reflex app.

Since we're using Buridan UI components which handle their own styling,
this module only contains the essential Reflex theme configuration.
"""

import reflex as rx

# Essential theme configuration
theme_config = rx.theme(
    appearance="light",
    accent_color="blue",
    gray_color="slate",
    radius="medium",
    scaling="100%",
    # Add Google Fonts import for better typography
    fonts={
        "Inter": "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap",
    }
) 