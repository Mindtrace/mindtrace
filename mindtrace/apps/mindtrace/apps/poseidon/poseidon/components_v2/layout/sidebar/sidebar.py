# poseidon/components_v2/layout/sidebar.py
import reflex as rx
from collections import OrderedDict
from poseidon.styles.global_styles import SP, T
from poseidon.state.line_scope import ScopeState

NAV = [
    # Main
    {"section": "Main", "label": "Home", "icon": "home", "href": "/"},

    # Data Viewer - Line view should be line data
    {"section": "Data Viewer", "label": "Line view", "icon": "folder-kanban", "href": "/line-view"}, 
    {"section": "Data Viewer", "label": "Plant view", "icon": "scan-eye", "href": "/plant-view"},

    # Analytics
    {"section": "Analytics", "label": "Line insights", "icon": "database", "href": "/line-insights"},
    {"section": "Analytics", "label": "Plant insights", "icon": "trending-up-down", "href": "/plant-insights"},

    # Audit & Reports
    {"section": "Audit & Reports", "label": "Alerts", "icon": "badge-alert", "href": "/alerts"},
    # {"section": "Audit & Reports", "label": "Agent", "icon": "person-standing", "href": "/agent"},

    # pinned to bottom
    {"label": "Settings", "icon": "cog", "href": "/settings"},
]

SIDEBAR_W   = "80px"
ICON_BG     = "rgba(15,23,42,.06)"  # slate-ish
ACTIVE_GRAD = "linear-gradient(135deg, rgba(37,99,235,.12) 0%, rgba(99,102,241,.12) 100%)"

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

def _tile(label: str, icon: str, *, active: bool):
    icon_node = rx.box(
        rx.icon(tag=icon, size=20, color=rx.cond(active, T.accent, T.fg)),
        width="40px",
        height="40px",
        display="grid",
        place_items="center",
        border_radius="12px",
        bg=rx.cond(active, ACTIVE_GRAD, ICON_BG),
        flex_shrink="0",
    )
    text_node = rx.text(
        label,
        size="1",
        weight="medium",
        color=rx.cond(active, T.accent, T.fg),
        text_align="center",
        line_height="1.1",
        margin_top="6px",
        wrap="balance",
    )
    return rx.box(
        rx.vstack(icon_node, text_node, gap="6px", align="center", justify="center", width="100%"),
        position="relative",
        padding=f"{SP.space_2} {SP.space_2}",
        border_radius=T.r_lg,
        bg=rx.cond(active, ACTIVE_GRAD, "transparent"),
        _hover={"bg": ACTIVE_GRAD, "color": T.accent},
        transition="all .16s ease",
        width="100%",
        display="flex",
        align_items="center",
        justify_content="center",
    )

def _nav_link(item: dict, *, active: bool):
    label, icon = item["label"], item["icon"]
    href, scope, to = item.get("href"), item.get("scope"), item.get("to")
    tile = _tile(label, icon, active=active)
    link = (
        rx.link(tile, href=href or "#", color="inherit", text_decoration="none", width="100%", display="block")
        if not (scope and to)
        else rx.link(
            tile,
            href=_scoped_href(scope, to),
            pointer_events=rx.cond(ScopeState.links_ready, "auto", "none"),
            opacity=rx.cond(ScopeState.links_ready, "1", "0.6"),
            color="inherit",
            text_decoration="none",
            width="100%",
            display="block",
        )
    )
    return rx.tooltip(link, content=label, side="right")

def _section_heading(title: str):
    return rx.text(
        title,
        font_size="9px",
        weight="bold",
        color=T.colors.fg_muted,
        letter_spacing=".08em",
        text_transform="uppercase",
        margin_bottom=SP.space_2,
        opacity="0.9",
        text_align="center",
    )

def Sidebar(*, active: str):
    settings_item = next((i for i in NAV if i["label"] == "Settings"), None)
    main_items    = [i for i in NAV if i["label"] != "Settings"]

    grouped: "OrderedDict[str, list[dict]]" = OrderedDict()
    for item in main_items:
        section = item.get("section", "")
        grouped.setdefault(section, []).append(item)

    section_nodes = []
    for section_title, items in grouped.items():
        heading = _section_heading(section_title) if section_title else rx.fragment()
        tiles = [_nav_link(i, active=(i["label"] == active)) for i in items]
        section_nodes.append(
            rx.vstack(
                heading,
                *tiles,
                align="stretch",
                gap="10px",
            )
        )

    sections_stack = rx.vstack(
        *section_nodes,
        gap=SP.space_3,
        width="100%",
    )

    settings_node = (
        _nav_link(settings_item, active=(settings_item and settings_item["label"] == active))
        if settings_item else rx.fragment()
    )

    return rx.box(
        rx.vstack(
            rx.box(
                sections_stack,
                overflow_y="auto",
                flex="1 1 0",
                min_height=0,
                padding=SP.space_3,
                padding_bottom=SP.space_2,
                overscroll_behavior="contain",
            ),
            rx.divider(margin=f"{SP.space_3} 0"),
            rx.box(
                settings_node,
                padding=SP.space_3,
                padding_top=SP.space_2,
            ),
            height="100%",
            width="100%",
            align_items="stretch",
            gap="0",
        ),
        width=SIDEBAR_W,
        min_width=SIDEBAR_W,
        bg=T.surface,
        border_right=f"1px solid {T.border}",
        position="sticky",
        top=T.header_h,
        height=f"calc(100vh - {T.header_h})",
        overscroll_behavior="none",
        as_="nav",
        aria_label="Primary",
        display="flex",
        flex_direction="column",
    )
