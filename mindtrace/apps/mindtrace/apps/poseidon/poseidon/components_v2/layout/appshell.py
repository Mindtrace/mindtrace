import reflex as rx
from .header import Header
from .sidebar.sidebar import Sidebar
from poseidon.styles.global_styles import T


def AppShell(
    *,
    body: rx.Component,
    title: str,
    sidebar_active: str,
    header_right: rx.Component | None = None,
    subheader: rx.Component | None = None,
) -> rx.Component:
    main = rx.hstack(
        Sidebar(active=sidebar_active),
        rx.box(
            body,
            padding=T.content_pad,
            width="100%",
            min_h=f"calc(100vh - {T.header_h})",
        ),
        align="start",
    )
    return rx.box(
        Header(title=title, right_slot=header_right),
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
    )
