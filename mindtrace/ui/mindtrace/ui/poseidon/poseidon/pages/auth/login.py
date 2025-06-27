"""
Modern login page component.

Provides user authentication interface with:
- Clean, modern form design using unified Poseidon UI components
- Email and password input fields
- Form validation and error handling
- Responsive design using modern design system
- Consistent with dashboard template styling
"""

import reflex as rx
from poseidon.state.auth import AuthState
from poseidon.components import login_form, centered_form_layout, redirect_component


def login_content() -> rx.Component:
    """
    Modern login form content using unified Poseidon UI components.
    All state and event logic is handled in the page/state, not in the components.
    """
    return centered_form_layout(
        login_form(
            title="Sign in to Poseidon Toolkit",
            subtitle="Enter your credentials to access your workspace"
        ),
        max_width="450px"
    )


def login_page() -> rx.Component:
    """
    Login page with dynamic rendering - redirects authenticated users.
    Uses unified redirect and form layout components for consistency.
    """
    return rx.cond(
        AuthState.is_authenticated,
        redirect_component("Redirecting to dashboard..."),
        login_content(),
    ) 