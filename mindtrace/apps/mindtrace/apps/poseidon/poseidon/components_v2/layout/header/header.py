import reflex as rx
from typing import Optional

from poseidon.components_v2.layout.header.profile_menu import ProfileMenu
from poseidon.components_v2.layout.header.scope_selector import ScopeSelector
from poseidon.styles.global_styles import T
from poseidon.styles.variants import COMPONENT_VARIANTS


def Header(
    *,
    title: str,
    right_slot: Optional[rx.Component] = None,
    show_scope_selector: bool = False,
) -> rx.Component:
    # Inline branding (same structure, 15px font)
    def logo_neuroforge() -> rx.Component:
        return rx.box(
            rx.hstack(
                rx.vstack(
                    rx.text(
                        "NeuroForge",
                        font_size="26px",
                        style=COMPONENT_VARIANTS["logo"]["title"],
                    ),
                    align="start",
                    margin_left="1rem",
                ),
                align="center",
                spacing="0",
            ),
            # keep header compact
            margin_bottom="0",
            width="auto",
        )

    left = rx.hstack(
        rx.image(src="/mindtrace-logo.png", height="64px", width="auto"),
        logo_neuroforge(),
        # rx.text(title, weight="medium", size="4"),
        gap="0",
        align="center",
    )

    right_children: list[rx.Component] = []
    if right_slot is not None:
        right_children.append(right_slot)
    if show_scope_selector:
        right_children.append(ScopeSelector())
    right_children.append(ProfileMenu())

    return rx.hstack(
        left,
        rx.spacer(),
        *right_children,
        gap=T.space_3,
        align="center",
        padding=f"{T.space_4} {T.space_6}",
        height=T.header_h,
        width="100%",
        bg=T.surface,
        border_bottom=f"1px solid {T.border}",
        position="sticky",
        top="0",
        z_index=str(T.z_header),
        overscroll_behavior="none",
    )
