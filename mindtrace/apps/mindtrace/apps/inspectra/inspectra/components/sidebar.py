from collections import OrderedDict

import reflex as rx

from inspectra.styles.global_styles import DS

# ──────────────────────────────── Navigation Data ────────────────────────────────
NAV = [
    {"section": "Main", "label": "Home", "icon": "home", "href": "/"},
    {"section": "Data Viewer", "label": "Plant view", "icon": "scan_eye", "href": "/plant-view"},
    {"section": "Data Viewer", "label": "Line view", "icon": "folder_kanban", "href": "/line-view"},
    {"section": "Analytics", "label": "Line insights", "icon": "database", "href": "/line-insights"},
    {"section": "Audit & Reports", "label": "Alerts", "icon": "badge_alert", "href": "/alerts"},
    {"section": "Audit & Reports", "label": "Reports", "icon": "trending_up_down", "href": "/reports"},
    {"label": "Settings", "icon": "cog", "href": "/settings"},
]


# ──────────────────────────────── Tile Component ────────────────────────────────
def _tile(label: str, icon: str, *, active: bool) -> rx.Component:
    """Sidebar tile with semantic color and hover motion."""
    bg_color = rx.cond(active, DS.color.brand, "transparent")
    icon_color = rx.cond(active, DS.color.surface, DS.color.text_primary)
    text_color = rx.cond(active, DS.color.surface, DS.color.text_primary)
    border_color = rx.cond(active, DS.color.brand, DS.color.border)

    return rx.box(
        rx.vstack(
            rx.box(
                rx.icon(tag=icon, size=22, color=icon_color),
                width="42px",
                height="42px",
                display="grid",
                place_items="center",
                border_radius=DS.radius.md,
                bg=bg_color,
                border=f"1px solid {border_color}",
                transition="all .15s ease",
            ),
            rx.text(
                label,
                font_size=DS.text.size_sm,
                color=text_color,
                text_align="center",
                weight="medium",
            ),
            align="center",
            justify="center",
            spacing=DS.space_token.sm,
            width="100%",
        ),
        border_radius=DS.radius.md,
        padding=f"{DS.space_px.xs} {DS.space_px.sm}",
        _hover={
            "bg": rx.cond(active, DS.color.brand, "rgba(0,0,0,0.04)"),
            "cursor": "pointer",
            "transition": "all .15s ease",
        },
        transition="all .15s ease",
        width="84px",
    )


# ──────────────────────────────── Navigation Sections ────────────────────────────────
def _nav_link(item: dict, *, active: bool) -> rx.Component:
    tile = _tile(item["label"], item["icon"], active=active)
    return rx.link(tile, href=item.get("href", "#"), text_decoration="none", width="100%")


def _section_heading(title: str) -> rx.Component:
    """Section heading with semantic text colors."""
    return rx.text(
        title.upper(),
        font_size=DS.text.size_sm,
        weight="bold",
        color=DS.color.text_secondary,
        letter_spacing=".06em",
        text_align="center",
        margin_bottom=DS.space_px.xs,
        margin_top=DS.space_px.xs,
    )


# ──────────────────────────────── Sidebar ────────────────────────────────
def Sidebar(*, active: str) -> rx.Component:
    """Main vertical navigation sidebar."""
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
                    spacing=DS.space_token.md,
                    padding_y=DS.space_px.sm,
                ),
                border_bottom=rx.cond(
                    i == len(grouped) - 1,
                    "none",
                    f"1px solid {DS.color.border}",
                ),
                padding_bottom=DS.space_px.sm,
            )
        )

    footer = rx.box(
        _nav_link(
            {"label": "Settings", "icon": "cog", "href": "/settings"},
            active=(active == "Settings"),
        ),
        padding=f"{DS.space_px.md} {DS.space_px.sm}",
        border_top=f"1px solid {DS.color.border}",
    )

    return rx.box(
        rx.vstack(
            *sections,
            align="stretch",
            spacing=DS.space_token.lg,
            padding=f"{DS.space_px.lg} {DS.space_px.sm}",
            flex="1 1 0",
            overflow_y="auto",
        ),
        footer,
        display="flex",
        flex_direction="column",
        justify_content="space-between",
        height=f"calc(100vh - {DS.layout.header_h})",
        width=DS.layout.sidebar_w,
        min_width=DS.layout.sidebar_w,
        bg=DS.color.surface,
        border_right=f"1px solid {DS.color.border}",
        position="sticky",
        top=DS.layout.header_h,
    )
