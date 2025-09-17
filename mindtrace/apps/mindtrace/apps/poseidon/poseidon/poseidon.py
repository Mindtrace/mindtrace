import reflex as rx

from poseidon.pages.auth import login_page, register_page
from poseidon.pages.camera import camera_configurator_page
from poseidon.pages.component_showcase import component_showcase_page
from poseidon.pages.dashboards import admin_page, super_admin_dashboard_page
from poseidon.pages.dashboards.line_insights import line_insights_page
from poseidon.pages.gallery import images_page
from poseidon.pages.index import index
from poseidon.pages.inference import inference_page
from poseidon.pages.management import (
    organization_management_page, project_management_page, user_management_page
)
from poseidon.pages.model_deployment import model_deployment_page
from poseidon.pages.user import profile_page
from poseidon.styles.styles import styles
from poseidon.styles.theme import theme_config
from poseidon.state.line_insights import LineInsightsState
from poseidon.pages.filter_table_demo import filter_table_demo
from poseidon.state.line_view_state import LineViewState

from poseidon.utils.app_loaders import (
    add_public_page,
    add_protected_page,
    add_admin_page,
    add_super_admin_page,
)

app = rx.App(theme=theme_config, style=styles)

# Home – protected dashboard (inside AppShell)
add_protected_page(
    app,
    route="/",
    body_fn=index,
    title="Mindtrace",
    active="Home",
)

# Auth pages – public (outside AppShell)
add_public_page(app, route="/login",    body_fn=login_page,    title="Mindtrace - Login")
add_public_page(app, route="/register", body_fn=register_page, title="Mindtrace - Register")

# Dashboards
add_admin_page(
    app,
    route="/admin",
    body_fn=admin_page,
    title="Mindtrace",
    active="Admin",
)

add_super_admin_page(
    app,
    route="/super-admin-dashboard",
    body_fn=super_admin_dashboard_page,
    title="Mindtrace",
    active="Super Admin Dashboard",
)

# Feature pages (protected)
add_protected_page(
    app,
    route="/camera-configurator",
    body_fn=camera_configurator_page,
    title="Mindtrace",
    active="Camera Configurator",
)
add_protected_page(
    app,
    route="/model-deployment",
    body_fn=model_deployment_page,
    title="Mindtrace",
    active="Model Deployment",
)
add_protected_page(
    app,
    route="/inference",
    body_fn=inference_page,
    title="Mindtrace",
    active="Inference Scanner",
)

# Management (choose admin/protected according to your RBAC)
add_admin_page(
    app,
    route="/organization-management",
    body_fn=organization_management_page,
    title="Mindtrace",
    active="Organization Management",
)
add_protected_page(
    app,
    route="/user-management",
    body_fn=user_management_page,
    title="Mindtrace",
    active="User Management",
)
add_protected_page(
    app,
    route="/project-management",
    body_fn=project_management_page,
    title="Mindtrace",
    active="Project Management",
)

# Analytics (protected + page-specific loaders)
add_protected_page(
    app,
    route="/plants/[plant_id]/lines/[line_id]/line-insights",
    body_fn=line_insights_page,
    title="Mindtrace",
    active="Line Insights",
    show_scope_selector=True,
    extra_on_load=[LineInsightsState.on_mount],
)
add_protected_page(
    app,
    route="/plants/[plant_id]/lines/[line_id]/line-view",
    body_fn=filter_table_demo,
    title="Mindtrace",
    active="Line View",
    show_scope_selector=True,
    extra_on_load=[LineViewState.load],
)

# User (protected)
add_protected_page(
    app,
    route="/profile",
    body_fn=profile_page,
    title="Mindtrace",
    active="Profile",
)
add_protected_page(
    app,
    route="/image-viewer",
    body_fn=images_page,
    title="Mindtrace",
    active="Image Viewer",
)

# Dev (protect or not as you wish)
add_protected_page(
    app,
    route="/component-showcase",
    body_fn=component_showcase_page,
    title="Mindtrace",
    active="Component Showcase",
)

from poseidon.backend.database.init import rebuild_all_models
rebuild_all_models()
