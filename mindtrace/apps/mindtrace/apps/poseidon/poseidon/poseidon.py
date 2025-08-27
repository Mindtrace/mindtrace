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

from poseidon.components_v2.layout.header.scope_selector import ScopeSelector
from poseidon.components_v2.layout.appshell import AppShell
from poseidon.pages.auth import login_page, register_admin_page, register_page, register_super_admin_page
from poseidon.pages.camera import camera_configurator_page
from poseidon.pages.component_showcase import component_showcase_page
from poseidon.pages.dashboards import admin_page, super_admin_dashboard_page
from poseidon.pages.gallery import images_page
from poseidon.pages.index import index
from poseidon.pages.inference import inference_page
from poseidon.pages.management import organization_management_page, project_management_page, user_management_page
from poseidon.pages.model_deployment import model_deployment_page
from poseidon.pages.user import profile_page
from poseidon.styles.styles import styles
from poseidon.styles.theme import theme_config

# Create app with comprehensive styling configuration
app = rx.App(
    theme=theme_config,
    style=styles,
)


def with_shell(body_fn, *, title, active, header_right_fn=None, subheader_fn=None, show_scope_selector=False):
    def wrapped():
        return AppShell(
            title=title,
            sidebar_active=active,
            header_right=header_right_fn() if header_right_fn else None,
            subheader=subheader_fn() if subheader_fn else None,
            body=body_fn(),
            show_scope_selector=show_scope_selector,
        )

    return wrapped


# Route definitions with descriptive titles
app.add_page(index, title="Mindtrace - Home", route="/")

# Auth routes
app.add_page(login_page, route="/login", title="Mindtrace - Login")
app.add_page(register_page, route="/register", title="Mindtrace - Register")
app.add_page(register_admin_page, route="/register-admin", title="Mindtrace - Admin Registration")
app.add_page(register_super_admin_page, route="/register-super-admin", title="Mindtrace - Super Admin Setup")

# Dashboard routes
app.add_page(with_shell(admin_page, title="Mindtrace - Admin", active="Admin"), route="/admin")
app.add_page(
    with_shell(super_admin_dashboard_page, title="Mindtrace - Super Admin Dashboard", active="Super Admin Dashboard"),
    route="/super-admin-dashboard",
)

# Camera Configurator route
app.add_page(
    with_shell(camera_configurator_page, title="Mindtrace - Camera Configurator", active="Camera Configurator", show_scope_selector=True),
    route="/camera-configurator",
)


# Model Deployment route
app.add_page(
    with_shell(model_deployment_page, title="Mindtrace - Model Deployment", active="Model Deployment"),
    route="/model-deployment",
)


# Inference route
app.add_page(
    with_shell(inference_page, title="Mindtrace - Inference Scanner", active="Inference Scanner"), route="/inference"
)

# Management routes
app.add_page(
    with_shell(user_management_page, title="Mindtrace - User Management", active="User Management"),
    route="/user-management",
)
app.add_page(
    with_shell(
        organization_management_page, title="Mindtrace - Organization Management", active="Organization Management"
    ),
    route="/organization-management",
)
app.add_page(
    with_shell(project_management_page, title="Mindtrace - Project Management", active="Project Management"),
    route="/project-management",
)

# User routes
app.add_page(with_shell(profile_page, title="Mindtrace - Profile", active="Profile"), route="/profile")
app.add_page(with_shell(images_page, title="Mindtrace - Image Viewer", active="Image Viewer"), route="/image-viewer")

#DEV
app.add_page(
    with_shell(component_showcase_page, title="Mindtrace - Component Showcase", active="Component Showcase"),
    route="/component-showcase",
)
