from typing import Optional

import reflex as rx

from inspectra.components.scope_selector import ScopeSelector
from inspectra.styles.global_styles import DS


# ───────────────────────────────────────────────
# 🔔 Notification Dropdown
# ───────────────────────────────────────────────
def NotificationDropdown() -> rx.Component:
    alerts = [
        {"icon": "triangle_alert", "title": "Defect rate exceeded threshold", "time": "1 min ago"},
        {"icon": "wrench", "title": "Maintenance scheduled", "time": "10 mins ago"},
        {"icon": "circle_alert", "title": "Model anomaly detected", "time": "30 mins ago"},
    ]

    return rx.dropdown_menu.root(
        rx.dropdown_menu.trigger(
            rx.icon(
                "bell",
                size=22,
                color=DS.color.brand,
                cursor="pointer",
                class_name="bell-icon",
            )
        ),
        rx.dropdown_menu.content(
            rx.box(
                rx.text("Notifications", weight="bold", size="3", color=DS.color.brand),
                rx.divider(margin_y=DS.space_px.sm),
                *[
                    rx.hstack(
                        rx.icon(a["icon"], color=DS.color.brand, size=16),
                        rx.box(
                            rx.text(a["title"], weight="medium", size="2", color=DS.color.text_primary),
                            rx.text(a["time"], size="1", color=DS.color.text_secondary),
                        ),
                        spacing=DS.space_token.sm,
                        align="start",
                    )
                    for a in alerts
                ],
                display="flex",
                flex_direction="column",
                gap=DS.space_px.sm,
            ),
            bg=DS.color.surface,
            padding=DS.space_px.md,
            border_radius=DS.radius.md,
            box_shadow="0 2px 8px rgba(0,0,0,.08)",
            min_width="280px",
        ),
        align="end",
    )


# ───────────────────────────────────────────────
# 🧭 Header Component
# ───────────────────────────────────────────────
def Header(
    title: Optional[str] = None,
    *,
    right_slot: Optional[rx.Component] = None,
    show_scope_selector: bool = False,
) -> rx.Component:
    """App header bar for all Inspectra pages."""

    left_section = rx.hstack(
        rx.image(src="/Inspectra.svg", height=DS.layout.header_h, width="auto"),
        rx.text(
            title or "Inspectra",
            weight="bold",
            size="5",
            color=DS.color.brand,
            margin_left=DS.space_px.sm,
        ),
        gap="0",
        align="center",
    )

    right_section = [
        ScopeSelector(),
        NotificationDropdown(),
        rx.avatar(
            fallback="U",
            color_scheme="green",
            size="6",
            border=f"2px solid {DS.color.brand_light}",
        ),
    ]

    if right_slot:
        right_section.insert(0, right_slot)

    return rx.hstack(
        left_section,
        rx.spacer(),
        *right_section,
        spacing=DS.space_token.md,
        align="center",
        padding=f"{DS.space_px.sm} {DS.space_px.lg}",
        height=DS.layout.header_h,
        width="100%",
        bg=DS.color.surface,
        border_bottom=f"1px solid {DS.color.border}",
        position="sticky",
        top="0",
        z_index=str(DS.z.header),
        overscroll_behavior="none",
    )
