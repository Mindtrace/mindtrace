"""Layout components for consistent page structure and responsive design.

Provides reusable layout patterns used across multiple pages:
- Page containers with sidebar spacing
- Authenticated page wrappers with redirect logic
- Content sections with consistent spacing
- Grid layouts for cards and content
"""

import reflex as rx

from poseidon.state.auth import AuthState
from poseidon.styles.global_styles import THEME
from poseidon.backend.database.models.enums import OrgRole


def page_container(*children, **props) -> rx.Component:
    """Standard page container with sidebar spacing and mindtrace background."""
    return rx.box(
        rx.box(*children, display="flex", flex_direction="column", gap=THEME.layout.content_gap, z_index="1", **props),
        min_height="100vh",
        position="relative",
        bg=THEME.colors.bg,
    )


def authenticated_page_wrapper(content_func, required_role=None) -> rx.Component:
    """Wrapper for pages that require authentication with optional role checking."""
    if required_role:
        # Map required roles to AuthState properties
        if required_role == OrgRole.ADMIN:
            return rx.box(
                rx.cond(
                    AuthState.is_authenticated & AuthState.is_admin,
                    content_func(),
                    rx.box("Redirecting...", on_mount=AuthState.redirect_if_not_admin),
                )
            )
        elif required_role == OrgRole.SUPER_ADMIN:
            return rx.box(
                rx.cond(
                    AuthState.is_authenticated & AuthState.is_super_admin,
                    content_func(),
                    rx.box("Redirecting...", on_mount=AuthState.redirect_if_not_super_admin),
                )
            )

    # For regular authentication check
    return rx.box(
        rx.cond(
            AuthState.is_authenticated,
            content_func(),
            rx.box("Redirecting...", on_mount=AuthState.redirect_if_not_authenticated),
        )
    )


def redirect_component(message: str = "Redirecting...") -> rx.Component:
    """Reusable redirect component with loading message."""
    return rx.box(
        message,
        on_mount=AuthState.redirect_if_authenticated,
        display="flex",
        align_items="center",
        justify_content="center",
        min_height="100vh",
        font_size="1.1rem",
        color=rx.color("gray", 11),
    )


def content_section(*children, **props) -> rx.Component:
    """Standard content section with consistent spacing."""
    return rx.box(
        *children,
        padding="1.5rem",
        border_radius="0.75rem",
        background=rx.color("gray", 2),
        border=f"1px solid {rx.color('gray', 6)}",
        **props,
    )


def two_column_layout(left_content, right_content, left_width="2fr", right_width="1fr") -> rx.Component:
    """Two-column responsive layout."""
    return rx.box(
        rx.box(left_content, grid_area="left"),
        rx.box(right_content, grid_area="right"),
        display="grid",
        grid_template_columns=f"{left_width} {right_width}",
        grid_template_areas='"left right"',
        gap="2rem",
        width="100%",
        # Responsive: stack on mobile
        **{
            "@media (max-width: 768px)": {
                "grid-template-columns": "1fr",
                "grid-template-areas": '"left" "right"',
            }
        },
    )


def three_column_grid(*children, **props) -> rx.Component:
    """Three-column responsive grid for cards."""
    return rx.box(
        *children, display="grid", grid_template_columns="repeat(auto-fit, minmax(300px, 1fr))", gap="1.5rem", **props
    )


def card_grid(*children, min_card_width="280px", **props) -> rx.Component:
    """Responsive card grid with customizable minimum card width."""
    return rx.box(
        *children,
        display="grid",
        grid_template_columns=f"repeat(auto-fit, minmax({min_card_width}, 1fr))",
        gap="2rem",
        justify_items="center",
        align_items="start",
        width="100%",
        **props,
    )


def centered_form_layout(form_content, max_width="400px") -> rx.Component:
    """Centered form layout for login/register pages."""
    return rx.center(
        form_content,
        min_height="100vh",
        background=rx.color("gray", 1),
        padding="2rem",
        max_width=max_width,
        margin="0 auto",
    )


def dashboard_layout(header, main_content, sidebar_content=None) -> rx.Component:
    """Standard dashboard layout with header and optional sidebar content."""
    if sidebar_content:
        return rx.box(
            header,
            rx.box(
                rx.box(main_content, flex="1"),
                rx.box(sidebar_content, width="300px", margin_left="2rem"),
                display="flex",
                gap="2rem",
            ),
            margin_left="16rem",
            padding="2rem",
            min_height="100vh",
            background=rx.color("gray", 1),
        )
    else:
        return page_container(
            header,
            main_content,
        )


def loading_wrapper(is_loading_var, loading_content, main_content) -> rx.Component:
    """Wrapper that shows loading state or main content."""
    return rx.cond(
        is_loading_var,
        rx.center(
            loading_content,
            min_height="200px",
            color=rx.color("gray", 11),
        ),
        main_content,
    )


def error_boundary(error_var, error_content, main_content) -> rx.Component:
    """Error boundary that shows error state or main content."""
    return rx.cond(
        error_var,
        rx.center(
            error_content,
            min_height="200px",
            color=rx.color("red", 11),
            padding="2rem",
        ),
        main_content,
    )
