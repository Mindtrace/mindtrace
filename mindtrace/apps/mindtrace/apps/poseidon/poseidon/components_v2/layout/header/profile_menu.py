import reflex as rx

from poseidon.state.auth import AuthState
from poseidon.styles.global_styles import T



def ProfileMenu() -> rx.Component:
    avatar = rx.box(
        AuthState.initials,
        width="32px",
        height="32px",
        bg=T.colors.ring,
        color=T.accent,
        border_radius=T.radius.r_md,
        display="flex",
        align_items="center",
        justify_content="center",
        font_weight=T.fw_600,
        font_size=T.fs_sm,
    )

    name_text = rx.text(
        rx.cond(AuthState.current_first_name, AuthState.current_first_name + " " + AuthState.current_last_name, "User"),
        font_weight=T.fw_400,
        color=T.fg,
        line_height="1",
    )
    email_text = rx.text(
        AuthState.email,
        color=T.fg_muted,
        font_size=T.fs_sm,
        line_height="1",
    )

    trigger_node = rx.hstack(
        avatar,
        name_text,
        rx.icon(tag="chevron-down", size=16, color=T.fg_subtle),
        gap=T.space_2,
        align_items="center",
        cursor="pointer",
        border_radius=T.r_full,
        padding=f"0 {T.space_1}",
        _hover={"background": T.surface_2},
    )

    content = rx.menu.content(
        rx.menu.item(
            rx.vstack(
                name_text,
                email_text,
                align_items="start",
                gap=T.space_1,
                width="100%",
            ),
            disabled=True,
            style={"cursor": "default", "padding": T.space_4},
        ),
        rx.menu.separator(),
        rx.menu.item(
            rx.hstack(
                rx.icon(tag="settings", size=18),
                rx.text("Settings"),
                gap=T.space_3,
                align_items="center",
            ),
            _hover={"background": T.ring, "color": T.accent},
            on_click=rx.redirect("/profile"),
        ),
        rx.menu.item(
            rx.hstack(
                rx.icon(tag="log-out", size=18),
                rx.text("Logout"),
                gap=T.space_3,
                align_items="center",
            ),
            _hover={"background": T.ring, "color": T.accent},
            on_click=AuthState.logout,
        ),
        bg=T.surface,
        border=f"1px solid {T.border}",
        border_radius=T.r_lg,
        box_shadow=T.shadow_2,
        min_width="280px",
        side="bottom",
        align="end",
    )

    return rx.cond(
        AuthState.is_authenticated,
        rx.menu.root(
            rx.menu.trigger(trigger_node),
            content,
        ),
        rx.link("Login", href="/login", color=T.accent),
    )
