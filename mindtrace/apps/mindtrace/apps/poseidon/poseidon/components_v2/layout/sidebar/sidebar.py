import reflex as rx
from collections import OrderedDict
from poseidon.styles.global_styles import SP, T
from poseidon.state.line_scope import ScopeState

# ─────────────────────────── Constants ────────────────────────────
SIDEBAR_W = "120px"

TEXT_PRIMARY = "#1a1a1a"
TEXT_SECONDARY = "#666666"
TEXT_MUTED = "#9ca3af"
BG_DEFAULT = "#f9f9f9"
BG_HOVER = "#ececec"
BG_ACTIVE = "#181818"
ICON_SIZE = 22

# ─────────────────────────── Tiles ────────────────────────────────
def _tile(label: str, icon: str, *, active: bool):
    active_bg = "#2a2a2a"   # softer black
    active_hover_bg = "#333333"
    inactive_bg = "transparent"
    hover_bg = "#ececec"

    icon_color = rx.cond(active, "#ffffff", "#1a1a1a")
    text_color = rx.cond(active, "#ffffff", "#1a1a1a")
    bg_color = rx.cond(active, active_bg, inactive_bg)

    icon_node = rx.box(
        rx.icon(
            tag=icon,
            size=22,
            color=icon_color,
            transition="color .15s ease",
        ),
        width="42px",
        height="42px",
        display="grid",
        place_items="center",
        border_radius="12px",
        bg=bg_color,
        border=rx.cond(active, "1px solid #1a1a1a", "1px solid rgba(0,0,0,0.05)"),
        box_shadow=rx.cond(active, "inset 0 0 0 1px rgba(255,255,255,0.05)", "none"),
    )

    text_node = rx.text(
        label,
        font_size="11px",
        weight="medium",
        color=text_color,
        text_align="center",
        line_height="1.2",
        wrap="balance",
        transition="color .15s ease",
    )

    return rx.box(
        rx.vstack(
            icon_node,
            text_node,
            gap="6px",
            align="center",
            justify="center",
            width="100%",
        ),
        border_radius="12px",
        padding=f"{SP.space_2} {SP.space_2}",
        bg=bg_color,
        _hover={
            "bg": rx.cond(active, active_hover_bg, hover_bg),
            "& svg": {"color": rx.cond(active, "#ffffff", "#000000")},
            "& p": {"color": rx.cond(active, "#ffffff", "#000000")},
            "cursor": "pointer",
            "transition": "all .15s ease",
        },
        transition="all .15s ease",
        width="84px",
    )




NAV = [
    {"section": "Main", "label": "Home", "icon": "home", "href": "/"},
    {"section": "Data Viewer", "label": "Plant view", "icon": "scan-eye", "href": "/plant-view"},
    {"section": "Data Viewer", "label": "Line view", "icon": "folder-kanban", "href": "/line-view"},
    {"section": "Analytics", "label": "Line insights", "icon": "database", "href": "/line-insights"},
    {"section": "Audit & Reports", "label": "Alerts", "icon": "badge-alert", "href": "/alerts"},
    {"section": "Audit & Reports", "label": "Reports", "icon": "trending-up-down", "href": "/reports"},
    {"label": "Settings", "icon": "cog", "href": "/settings"},
]

# ─────────────────────────── Helpers ──────────────────────────────
def _scoped_href(scope: str, to: str):
    to = to.lstrip("/")
    if scope == "line":
        return rx.cond(
            ScopeState.resolved_plant != "",
            rx.cond(
                ScopeState.resolved_line != "",
                "/plants/" + ScopeState.resolved_plant + "/lines/" + ScopeState.resolved_line + "/" + to,
                "/plants/" + ScopeState.resolved_plant + "/overview",
            ),
            "/overview",
        )
    if scope == "plant":
        return rx.cond(
            ScopeState.resolved_plant != "",
            "/plants/" + ScopeState.resolved_plant + "/" + to,
            "/overview",
        )
    return "/" + to

# ─────────────────────────── Links & Sections ─────────────────────
def _nav_link(item: dict, *, active: bool):
    label, icon = item["label"], item["icon"]
    href, scope, to = item.get("href"), item.get("scope"), item.get("to")
    tile = _tile(label, icon, active=active)
    link = (
        rx.link(tile, href=href or "#", text_decoration="none", width="100%")
        if not (scope and to)
        else rx.link(
            tile,
            href=_scoped_href(scope, to),
            pointer_events=rx.cond(ScopeState.links_ready, "auto", "none"),
            opacity=rx.cond(ScopeState.links_ready, "1", "0.6"),
            text_decoration="none",
            width="100%",
        )
    )
    return rx.tooltip(link, content=label, side="right")

def _section_heading(title: str):
    return rx.text(
        title.upper(),
        font_size="13px",
        weight="bold",
        color=TEXT_SECONDARY,
        letter_spacing=".06em",
        text_align="center",
        margin_bottom="8px",
        margin_top="6px",
    )

# ─────────────────────────── Main Sidebar ─────────────────────────
def Sidebar(*, active: str):
    settings_item = next((i for i in NAV if i["label"] == "Settings"), None)
    main_items = [i for i in NAV if i["label"] != "Settings"]

    grouped: "OrderedDict[str, list[dict]]" = OrderedDict()
    for item in main_items:
        section = item.get("section", "")
        grouped.setdefault(section, []).append(item)

    # Build section stacks
    section_nodes = []
    grouped_items = list(grouped.items())

    for i, (section_title, items) in enumerate(grouped_items):
        is_last = i == len(grouped_items) - 1

        heading = _section_heading(section_title) if section_title else rx.fragment()
        tiles = [_nav_link(item, active=(item["label"] == active)) for item in items]

        section_box = rx.box(
            rx.vstack(
                heading,
                *tiles,
                align="stretch",
                gap="10px",
                padding_y="8px",
            ),
            border_bottom=rx.cond(is_last, "none", "1px solid rgba(0,0,0,0.25)"),
            padding_bottom="12px",
            margin_bottom="6px",
        )

        section_nodes.append(section_box)

    # Scrollable main navigation
    sections_stack = rx.box(
        rx.vstack(*section_nodes, gap="16px", width="100%"),
        overflow_y="auto",
        flex="1 1 0",
        padding="18px 12px",
        overscroll_behavior="contain",
        min_height=0,
    )

    # Fixed bottom settings
    settings_node = (
        _nav_link(settings_item, active=(settings_item and settings_item["label"] == active))
        if settings_item
        else rx.fragment()
    )

    footer = rx.box(
        rx.divider(margin="8px 0", color="rgba(0,0,0,0.2)"),
        settings_node,
        padding="16px 12px",
    )

    # Final layout
    return rx.box(
        sections_stack,
        footer,
        display="flex",
        flex_direction="column",
        justify_content="space-between",
        align_items="stretch",
        height=f"calc(100vh - {T.header_h})",
        width=SIDEBAR_W,
        min_width=SIDEBAR_W,
        bg=BG_DEFAULT,
        border_right="1px solid rgba(0,0,0,0.15)",
        position="sticky",
        top=T.header_h,
    )
