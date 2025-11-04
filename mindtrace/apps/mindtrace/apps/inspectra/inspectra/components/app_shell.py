import reflex as rx
from inspectra.components.header import Header
from inspectra.components.sidebar import Sidebar
from inspectra.state.shell_state import ShellState
from inspectra.state.auth_state import AuthState
from inspectra.utils.get_active_label import get_active_label
from inspectra.styles.global_styles import T


def AppShell(content: rx.Component) -> rx.Component:
    """Main layout wrapper that enforces auth and wraps protected pages."""
    path = ShellState.current_path

    redirect_condition = (~AuthState.logged_in) & (~ShellState.is_public)

    return rx.cond(
        redirect_condition,
        rx.fragment(rx.box(on_mount=rx.redirect("/login"))),
        rx.cond(
            ShellState.is_public,
            rx.box(
                content,
                width="100%",
                min_height="100vh",
                bg=T.background,
            ),
            rx.vstack(
                Header(),
                rx.hstack(
                    Sidebar(active=get_active_label(path)),
                    rx.box(
                        content,
                        flex="1",
                        padding="24px",
                        overflow_y="auto",
                        bg=T.background,
                        min_height=f"calc(100vh - {T.header_h})",
                    ),
                    width="100%",
                    align="start",
                ),
                width="100%",
                height="100vh",
                spacing="0",
                align="start",
            ),
        ),
    )
