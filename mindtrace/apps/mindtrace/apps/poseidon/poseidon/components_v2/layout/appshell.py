import reflex as rx

from poseidon.styles.global_styles import T
from poseidon.state.auth import AuthState
from poseidon.state.line_scope import ScopeState

from .header.header import Header
from .sidebar.sidebar import Sidebar


def AppShell(
    *,
    body: rx.Component,
    title: str,
    sidebar_active: str,
    header_right: rx.Component | None = None,
    subheader: rx.Component | None = None,
    show_scope_selector: bool = False,
) -> rx.Component:
    main = rx.hstack(
        Sidebar(active=sidebar_active),
        rx.box(
            body,
            # padding=T.content_pad,
            width="100%",
            min_h=f"calc(100vh - {T.header_h})",
        ),
        align="start",
        gap="0",
    )
    return rx.box(
        Header(title=title, right_slot=header_right, show_scope_selector=show_scope_selector),
        rx.cond(
            subheader is not None,
            rx.box(
                subheader,
                bg=T.colors.surface,
                border_bottom=f"1px solid {T.border}",
                padding=f"{T.space_3} {T.space_6}",
            ),
        ),
        main,
        bg=T.bg,
        min_h="100vh",
        overscroll_behavior="none",
        on_mount=lambda: ScopeState.ensure_directory(
            AuthState.user_organization_id,  # org_id
        ),
    )
