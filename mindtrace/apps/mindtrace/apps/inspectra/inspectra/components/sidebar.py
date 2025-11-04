from collections import OrderedDict

import reflex as rx

from inspectra.styles.global_styles import SP, T

# ──────────────────────────────── Navigation Data ────────────────────────────────
NAV = [
    {"section": "Main", "label": "Home", "icon": "home", "href": "/"},
    {"section": "Data Viewer", "label": "Plant view", "icon": "scan-eye", "href": "/plant-view"},
    {"section": "Data Viewer", "label": "Line view", "icon": "folder-kanban", "href": "/line-view"},
    {"section": "Analytics", "label": "Line insights", "icon": "database", "href": "/line-insights"},
    {"section": "Audit & Reports", "label": "Alerts", "icon": "badge-alert", "href": "/alerts"},
    {"section": "Audit & Reports", "label": "Reports", "icon": "trending-up-down", "href": "/reports"},
    {"label": "Settings", "icon": "cog", "href": "/settings"},
]


# ──────────────────────────────── Tile Component ────────────────────────────────
def _tile(label: str, icon: str, *, active: bool):
    bg_color = rx.cond(active, T.primary, "transparent")
    icon_color = rx.cond(active, "#ffffff", "#1a1a1a")
    text_color = rx.cond(active, "#ffffff", "#1a1a1a")

    return rx.box(
        rx.vstack(
            rx.box(
                rx.icon(tag=icon, size=22, color=icon_color),
                width="42px",
                height="42px",
                display="grid",
                place_items="center",
                border_radius=T.border_radius,
                bg=bg_color,
                border=rx.cond(active, f"1px solid {T.primary}", "1px solid rgba(0,0,0,0.05)"),
            ),
            rx.text(label, font_size="11px", color=text_color, text_align="center", weight="medium"),
            align="center",
            justify="center",
            gap=SP.space_2,
            width="100%",
        ),
        border_radius=T.border_radius,
        padding=f"{SP.space_2} {SP.space_2}",
        _hover={
            "bg": rx.cond(active, T.primary, "rgba(0,0,0,0.05)"),
            "cursor": "pointer",
            "transition": "all .15s ease",
        },
        transition="all .15s ease",
        width="84px",
    )


# ──────────────────────────────── Navigation Sections ────────────────────────────────
def _nav_link(item: dict, *, active: bool):
    tile = _tile(item["label"], item["icon"], active=active)
    return rx.link(tile, href=item.get("href", "#"), text_decoration="none", width="100%")


def _section_heading(title: str):
    return rx.text(
        title.upper(),
        font_size="13px",
        weight="bold",
        color="#666",
        letter_spacing=".06em",
        text_align="center",
        margin_bottom="8px",
        margin_top="6px",
    )


# ──────────────────────────────── Sidebar ────────────────────────────────
def Sidebar(*, active: str):
    grouped = OrderedDict()
    for item in NAV:
        section = item.get("section", "")
        grouped.setdefault(section, []).append(item)

    sections = []
    for i, (section, items) in enumerate(grouped.items()):
        heading = _section_heading(section) if section else rx.fragment()
        tiles = [_nav_link(it, active=(it["label"] == active)) for it in items]
        sections.append(
            rx.box(
                rx.vstack(
                    heading,
                    *tiles,
                    align="stretch",
                    gap="10px",
                    padding_y="8px",
                ),
                border_bottom=rx.cond(i == len(grouped) - 1, "none", "1px solid rgba(0,0,0,0.1)"),
                padding_bottom="12px",
            )
        )

    footer = rx.box(
        _nav_link({"label": "Settings", "icon": "cog", "href": "/settings"}, active=(active == "Settings")),
        padding="16px 12px",
        border_top="1px solid rgba(0,0,0,0.1)",
    )

    return rx.box(
        rx.vstack(*sections, align="stretch", gap="16px", padding="18px 12px", flex="1 1 0", overflow_y="auto"),
        footer,
        display="flex",
        flex_direction="column",
        justify_content="space-between",
        height=f"calc(100vh - {T.header_h})",
        width=T.sidebar_w,
        min_width=T.sidebar_w,
        bg=T.surface,
        border_right=f"1px solid {T.border}",
        position="sticky",
        top=T.header_h,
    )
