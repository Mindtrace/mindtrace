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
from poseidon.pages.index import index
from poseidon.pages.login import login_page
from poseidon.pages.register import register_page, register_admin_page, register_super_admin_page
from poseidon.pages.profile import profile_page
from poseidon.pages.admin import admin_page
from poseidon.pages.user_management import user_management_page
from poseidon.pages.super_admin import super_admin_page
from poseidon.styles.theme import theme_config
from poseidon.styles.styles import styles

# Create app with comprehensive styling configuration
app = rx.App(
    theme=theme_config,
    style=styles,
)

# Route definitions with descriptive titles
app.add_page(index, route="/", title="MindTrace - Home")
app.add_page(login_page, route="/login", title="MindTrace - Login")
app.add_page(register_page, route="/register", title="MindTrace - Register")
app.add_page(register_admin_page, route="/register-admin", title="MindTrace - Admin Registration")
app.add_page(register_super_admin_page, route="/register-super-admin", title="MindTrace - Super Admin Setup")
app.add_page(profile_page, route="/profile", title="MindTrace - Profile")
app.add_page(admin_page, route="/admin", title="MindTrace - Admin")
app.add_page(user_management_page, route="/user-management", title="MindTrace - User Management")
app.add_page(super_admin_page, route="/super-admin", title="MindTrace - Super Admin")

# Add your main/data viewer page here as needed 