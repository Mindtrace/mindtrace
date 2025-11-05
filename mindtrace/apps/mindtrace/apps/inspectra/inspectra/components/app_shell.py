import reflex as rx

from inspectra.components.header import Header
from inspectra.components.sidebar import Sidebar
from inspectra.state.auth_state import AuthState
from inspectra.state.shell_state import ShellState
from inspectra.styles.global_styles import DS
from inspectra.utils.get_active_label import get_active_label


def AppShell(content: rx.Component) -> rx.Component:
    """Main application shell that enforces authentication and wraps protected pages."""
    path = ShellState.current_path
    should_redirect = (~AuthState.logged_in) & (~ShellState.is_public)

    return rx.cond(
        should_redirect,
        rx.box(on_mount=rx.redirect("/login")),
        rx.cond(
            ShellState.is_public,
            rx.box(
                content,
                width="100%",
                min_height="100vh",
                bg=DS.color.background,
            ),
            rx.vstack(
                Header(),
                rx.hstack(
                    Sidebar(active=get_active_label(path)),
                    rx.box(
                        content,
                        flex="1",
                        padding=DS.space_px.lg,
                        overflow_y="auto",
                        bg=DS.color.background,
                        min_height=f"calc(100vh - {DS.layout.header_h})",
                    ),
                    width="100%",
                    align="start",
                ),
                width="100%",
                height="100vh",
                spacing=DS.space_token.none if hasattr(DS.space_token, "none") else "0",  # safe fallback
                align="start",
                bg=DS.color.surface,
            ),
        ),
    )
