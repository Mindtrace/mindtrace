"""
Modern split login page (Mindtrace-style).

- Left: logo, tag line, and your existing login_form
- Right: gradient panel with wordmark and marketing bullets
- Fully responsive; stacks on narrow screens
"""

import reflex as rx

from poseidon.components_v2.branding import logo_neuroforge  # (unused, but keep if referenced elsewhere)
from poseidon.components_v2.core import loader
from poseidon.components_v2.layout import main_css_animation
from poseidon.state.auth import AuthState

from .components.auth_headers import auth_headers
from .components.login_form import login_form


# ----------------------------- UI helpers --------------------------------------

def _bullet(title: str, desc: str) -> rx.Component:
    return rx.vstack(
        rx.text(title, weight="bold", size="3"),
        rx.text(desc, size="2", opacity=".9"),
        spacing="1",
        align="start",
        width="100%",
    )


def _right_panel() -> rx.Component:
    """Gradient marketing panel."""
    return rx.box(
        rx.vstack(
            # Wordmark
            rx.hstack(
                rx.icon("brain-circuit", size=26),
                rx.text("mindtrace.ai", weight="bold", size="6"),
                align="center",
                spacing="3",
            ),
            rx.box(height="10px"),
            rx.text("Unparalleled knowledge of AI technologies", weight="bold", size="4"),

            rx.box(height="18px"),

            _bullet("AI Modeling using Unlabeled Data",
                    "AI models that learn new use cases with less data tagging."),
            _bullet("Continuous Learning",
                    "Consolidate new use case knowledge continuously."),
            _bullet("Few-shot Incremental Learning",
                    "Use-case specific AI brains learn with few samples and without full re-runs."),
            _bullet("Growing Enhanced AI Brain Library",
                    "Start with enhanced, pre-trained models for specific use cases."),

            spacing="4",
            align="start",
            width="100%",
        ),
        color="white",
        padding="36px",
        background="linear-gradient(135deg, #3B82F6 0%, #60A5FA 40%, #2563EB 100%)",
        background_size="200% 200%",
        animation="loginGradient 18s ease infinite",
        height="100%",
    )


def _left_panel() -> rx.Component:
    """Logo + tagline + login form (uses existing login_form component)."""
    return rx.box(
        rx.vstack(
            # Big circular logo
            rx.box(
                rx.image(src="/mindtrace-logo.png", width="auto", height="160px"),
                logo_neuroforge(),
                # width="200px",
                # height="200px",
                # border_radius="9999px",
                # background="#0f1b3d",
                display="grid",
                place_items="center",
                # box_shadow="0 8px 28px rgba(2,6,23,.12) inset, 0 6px 18px rgba(2,6,23,.08)",
            ),

            rx.text("THE HOME OF BRAIN-INSPIRED AI",
                    weight="bold",
                    letter_spacing=".08em",
                    transform="uppercase",
                    # margin_top="18px",
                    size="3"),

            # rx.box(height="18px"),
            rx.text("Please login to your account", color="var(--gray-11)"),

            # Your existing form (email/password + sign-in button)
            rx.box(
                login_form(title="", subtitle=""),
                width="100%",
                margin_top="12px",
            ),

            # "Forgot password?"
            rx.link("Forgot password?", href="/forgot-password", color="var(--indigo-11)", margin_top="8px"),

            spacing="4",
            align="center",
            width="100%",
        ),
        padding="36px",
        bg="white",
        height="100%",
    )


def _shell_styles() -> rx.Component:
    """Page-level CSS (gradient animation + layout polish)."""
    return rx.html(
        """
        <style>
          @keyframes loginGradient {
            0% { background-position: 0% 50%; }
            50%{ background-position: 100% 50%; }
            100%{ background-position: 0% 50%; }
          }
        </style>
        """
    )


def login_content() -> rx.Component:
    """
    Split card with left form and right gradient panel.
    Stacks to single column on small screens.
    """
    return rx.center(
        rx.box(
            # Outer container with rounded card feel
            rx.grid(
                _left_panel(),
                _right_panel(),
                columns="repeat(auto-fit, minmax(360px, 1fr))",
                width="100%",
                height="100%",
            ),
            width="min(1080px, 96vw)",
            min_height="560px",
            border_radius="16px",
            overflow="hidden",
            bg="white",
            box_shadow="0 12px 36px rgba(2,6,23,.10)",
        ),
        width="100%",
        min_height="100vh",
        padding="24px",
        bg="#f3f4f6",
    )


# ----------------------------- Page --------------------------------------------

def login_page() -> rx.Component:
    """Redirects if already authenticated; otherwise shows split login."""
    return rx.box(
        _shell_styles(),
        rx.cond(
            AuthState.is_authenticated,
            loader(size="large", variant="primary"),
            login_content(),
        ),
        main_css_animation(),
    )
