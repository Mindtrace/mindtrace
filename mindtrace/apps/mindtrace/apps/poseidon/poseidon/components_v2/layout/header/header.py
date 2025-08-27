import reflex as rx

from poseidon.components_v2.layout.header.profile_menu import ProfileMenu
from poseidon.styles.global_styles import T

from poseidon.components_v2.layout.header.scope_selector import ScopeSelector

def Header(*, title: str, right_slot: rx.Component | None = None, show_scope_selector: bool = False) -> rx.Component:
    return rx.hstack(
        rx.hstack(
            rx.box(width="32px", height="32px", bg=T.accent, border_radius="10px"),
            rx.text(title, font_weight=T.fw_600, text_align="center"),
            gap=T.space_3,
            align_items="center",
            justify_content="center",
        ),
        rx.spacer(),
        right_slot or rx.box(),
        ScopeSelector() if show_scope_selector else rx.box(),
        ProfileMenu(),
        padding=f"{T.space_4} {T.space_6}",
        height=T.header_h,
        bg=T.surface,
        border_bottom=f"1px solid {T.border}",
        position="sticky",
        top="0",
        z_index=str(T.z_header),
        overscroll_behavior="none",
        gap=T.space_3,
    )
