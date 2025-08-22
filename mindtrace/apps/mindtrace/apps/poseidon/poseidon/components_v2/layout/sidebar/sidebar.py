import reflex as rx
from poseidon.styles.global_styles import SP, T

from .sidebar_state import SidebarState as S

NAV = [
    (
        "Main",
        [
            {"label": "Camera Configurator", "icon": "camera", "href": "/camera-configurator"},
            {"label": "Model Deployment", "icon": "layout-panel-left", "href": "/model-deployment"},
            {"label": "Inference Scanner", "icon": "wrench", "href": "/inference"},
            {"label": "Image Viewer", "icon": "image", "href": "/image-viewer"},
        ],
    ),
    (
        "Analytics",
        [
            {"label": "Line Insights", "icon": "chart-line", "href": "/line-insights"},
        ],
    ),
    (
        "Admin",
        [
            {"label": "Organization Management", "icon": "alarm-clock", "href": "/organization-management"},
            {"label": "Project Management", "icon": "file-text", "href": "/project-management"},
            {"label": "Profile", "icon": "user", "href": "/profile"},
            {"label": "User Management", "icon": "shield-check", "href": "/user-management"},
        ],
    ),
    (
        "Developer",
        [
            {"label": "Component Showcase", "icon": "image", "href": "/component-showcase"},
        ],
    ),
]

# Theme-based paddings
H_PAD = SP.space_3
V_PAD = SP.space_2
ACTIVE_BG = "rgba(0,87,255,.08)"


def _active_bar():
    return rx.box(
        position="absolute", left="0", top=V_PAD, bottom=V_PAD, width="3px", bg=T.accent, border_radius=T.r_full
    )


def _nav_row(label: str, icon: str, active: bool, collapsed):
    icon_size_px = "20px"
    icon_node = rx.box(
        rx.icon(tag=icon, size=20, color="currentColor"),
        width=icon_size_px,
        height=icon_size_px,
        display="grid",
        place_items="center",
        flex_shrink="0",
    )
    content = rx.hstack(
        icon_node,
        rx.cond(collapsed, rx.box(width="0px"), rx.text(label, size="2", color="inherit")),
        gap=rx.cond(collapsed, "0", T.space_3),
        align="center",
    )
    return rx.box(
        rx.cond(active, _active_bar(), rx.box()),
        content,
        position="relative",
        padding=f"{V_PAD} {H_PAD}",
        border_radius=T.r_md,
        color=rx.cond(active, T.accent, T.fg),
        bg=rx.cond(active, ACTIVE_BG, "transparent"),
        _hover={"bg": ACTIVE_BG, "color": T.accent},
        font_weight=rx.cond(active, T.fw_600, T.fw_500),
        width="100%",
    )


def _nav_item(*, label: str, icon: str, href: str, active: bool, collapsed):
    row = _nav_row(label, icon, active, collapsed)
    row = rx.cond(collapsed, rx.tooltip(row, content=label, side="right"), row)
    return rx.link(
        row,
        href=href,
        color="inherit",
        text_decoration="none",
        aria_current="page" if active else "false",
        width="100%",
    )


def _section(*, title: str, items: list[dict], active_label: str, collapsed):
    title_node = rx.cond(
        collapsed,
        rx.box(height="6px"),
        rx.hstack(
            rx.text(title, size="1", color=T.fg_muted, padding=f"0 {T.space_2}"),
            rx.box(flex_grow="1", height="1px", bg=T.border, opacity="0.8"),
            align="center",
            gap=T.space_2,
            padding_right=T.space_2,
        ),
    )
    nodes = [title_node]
    for i in items:
        nodes.append(
            _nav_item(
                label=i["label"],
                icon=i["icon"],
                href=i["href"],
                active=(i["label"] == active_label),
                collapsed=collapsed,
            )
        )
    return rx.vstack(*nodes, gap="6px", width="100%", align_items="stretch")


def Sidebar(*, active: str):
    toggle = rx.tooltip(
        rx.button(
            rx.cond(
                S.collapsed,
                rx.icon(tag="chevron-right", size=18),
                rx.icon(tag="chevron-left", size=18),
            ),
            on_click=S.toggle,
            padding=f"{V_PAD}",
            border_radius=T.r_full,
            bg=T.surface,
            color=T.fg,
            border=f"1px solid {T.border}",
            _hover={"bg": "rgba(0,87,255,.1)", "color": T.accent},
            width="36px",
            height="36px",
            min_width="36px",
            position="absolute",
            right="-16px",
            top=T.space_4,
            z_index="2",
        ),
        content=rx.cond(S.collapsed, "Expand", "Collapse"),
        side="right",
        cursor="pointer",
    )

    sections = [_section(title=t, items=it, active_label=active, collapsed=S.collapsed) for t, it in NAV]
    nav_scroll = rx.vstack(*sections, gap="8px", padding=T.space_4, overflow_y="auto", overscroll_behavior="none")

    return rx.box(
        toggle,
        nav_scroll,
        width=rx.cond(S.collapsed, T.sidebar_w_collapsed, T.sidebar_w),
        min_width=rx.cond(S.collapsed, T.sidebar_w_collapsed, T.sidebar_w),
        bg=T.surface,
        border_right=f"1px solid {T.border}",
        position="sticky",
        top=T.header_h,
        height=f"calc(100vh - {T.header_h})",
        overscroll_behavior="none",
        as_="nav",
        aria_label="Primary",
    )
