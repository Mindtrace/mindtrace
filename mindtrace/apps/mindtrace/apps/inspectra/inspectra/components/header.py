from typing import Optional

import reflex as rx

from inspectra.styles.global_styles import T


def NotificationDropdown() -> rx.Component:
    alerts = [
        {"icon": "alert-triangle", "title": "Defect rate exceeded threshold", "time": "1 min ago"},
        {"icon": "wrench", "title": "Maintenance scheduled", "time": "10 mins ago"},
        {"icon": "circle-alert", "title": "Model anomaly detected", "time": "30 mins ago"},
    ]
    return rx.dropdown_menu.root(
        rx.dropdown_menu.trigger(
            rx.icon("bell", size=22, color="#184937", cursor="pointer", class_name="bell-icon"),
        ),
        rx.dropdown_menu.content(
            rx.box(
                rx.text("Notifications", weight="bold", size="2", color="#184937"),
                rx.divider(margin_y="4px"),
                *[
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
                ],
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
    title: Optional[str] = None,
    *,
    right_slot: Optional[rx.Component] = None,
    show_scope_selector: bool = False,
) -> rx.Component:
    """App header bar."""
    left = rx.hstack(
        rx.image(src="/Inspectra.svg", height="64px", width="auto"),
        rx.text(title or "Inspectra", weight="bold", size="5", color="#184937", margin_left="8px"),
        gap="0",
        align="center",
    )

    right_children = [
        NotificationDropdown(),
        rx.avatar(fallback="U", color_scheme="green", size="6"),
    ]

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
