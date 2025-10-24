import reflex as rx
from typing import Optional

from poseidon.components_v2.layout.header.profile_menu import ProfileMenu
from poseidon.components_v2.layout.header.scope_selector import ScopeSelector
from poseidon.styles.global_styles import T
from poseidon.styles.variants import COMPONENT_VARIANTS

def _css() -> rx.Component:
    return rx.html("""
    <style>
    .bell-icon:hover {
  background: rgba(24,73,55,0.1);
  border-radius: 50%;
  transition: background 0.2s ease;
}
</style>
    """),

def NotificationDropdown() -> rx.Component:
    alerts = [
        {"icon": "alert-triangle", "title": "Defect rate exceeded threshold", "time": "1 min ago"},
        {"icon": "wrench", "title": "Maintenance scheduled", "time": "10 mins ago"},
        {"icon": "circle-alert", "title": "Model anomaly detected", "time": "30 mins ago"},
    ]

    items = [
        rx.hstack(
            rx.icon(a["icon"], color="#184937", size=16),
            rx.box(
                rx.text(a["title"], weight="medium", size="1", color="#0f172a"),
                rx.text(a["time"], size="1", color="#64748b"),
            ),
            spacing="3",
            align="start",
        )
        for a in alerts
    ]

    return rx.dropdown_menu.root(
        rx.dropdown_menu.trigger(
            rx.icon("bell", size=22, color="#184937", cursor="pointer", class_name="bell-icon"),
        ),
        rx.dropdown_menu.content(
            rx.box(
                rx.text("Notifications", weight="bold", size="2", color="#184937"),
                rx.divider(margin_y="4px"),
                *items,
                spacing="3",
                display="flex",
                flex_direction="column",
                gap="8px",
            ),
            bg="white",
            padding="12px",
            border_radius="8px",
            box_shadow="0 2px 8px rgba(0,0,0,.08)",
            min_width="280px",
        ),
        align="end",
    )



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
                        "Inspectra",
                        font_size="26px",
                        style=COMPONENT_VARIANTS["logo"]["title"],
                        color="#60CCA5",
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
        rx.image(src="/Inspectra.svg", height="64px", width="auto"),
        rx.text('Global Operations View', weight="bold", size="5", color="#184937", margin_left="8px"),
        # logo_neuroforge(),
        # rx.text(title, weight="medium", size="4"),
        gap="0",
        align="center",
    )

    right_children: list[rx.Component] = []
    if right_slot is not None:
        right_children.append(right_slot)
    # if show_scope_selector:
    right_children.append(ScopeSelector())
    right_children.append(NotificationDropdown())
    right_children.append(ProfileMenu())

    return rx.hstack(
        _css(),
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
