# poseidon/components_v2/layout/sidebar.py
import reflex as rx
from poseidon.styles.global_styles import SP, T
from poseidon.state.line_scope import ScopeState

NAV = [
    {"label": "Home",              "icon": "home",          "href": "/"},
    {"label": "Create Line",       "icon": "plus",          "href": "/create-line"},
    {"label": "Lines Deployed",    "icon": "shield-check",  "href": "/lines"},
    {"label": "Lines in Progress", "icon": "loader-circle", "href": "/lines-in-progress"},
    {"label": "Settings",          "icon": "cog",           "href": "/settings"},  # pinned to bottom
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

def Sidebar(*, active: str):
    settings_item = next((i for i in NAV if i["label"] == "Settings"), None)
    main_items    = [i for i in NAV if i["label"] != "Settings"]

    main_nodes    = [_nav_link(i, active=(i["label"] == active)) for i in main_items]
    settings_node = _nav_link(settings_item, active=(settings_item and settings_item["label"] == active)) if settings_item else rx.fragment()

    return rx.box(
        rx.vstack(
            *main_nodes,
            rx.spacer(),
            rx.divider(margin=f"{SP.space_3} 0"),
            settings_node,
            gap="10px",
            padding=SP.space_3,
            width="100%",
            height="100%",
            align_items="stretch",
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
