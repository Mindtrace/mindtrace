"""Main Reflex application configuration.

This module configures the complete web application with:
- Theme and styling system integration
- Route definitions for all pages
- Authentication-aware navigation
- Consistent design system implementation

The app uses a black and orange theme with clean, modern styling
and implements role-based authentication for secure access control.
"""

import reflex as rx
from reflex_app.pages.index import index
from reflex_app.pages.login import login_page
from reflex_app.pages.register import register_page
from reflex_app.pages.profile import profile_page
from reflex_app.pages.admin import admin_page
from reflex_app.styles import theme_config, styles

# Create app with comprehensive styling configuration
app = rx.App(
    theme=theme_config,
    style=styles,
)

# Route definitions with descriptive titles
app.add_page(index, route="/", title="MindTrace - Home")
app.add_page(login_page, route="/login", title="MindTrace - Login")
app.add_page(register_page, route="/register", title="MindTrace - Register")
app.add_page(profile_page, route="/profile", title="MindTrace - Profile")
app.add_page(admin_page, route="/admin", title="MindTrace - Admin")

# Add your main/data viewer page here as needed 