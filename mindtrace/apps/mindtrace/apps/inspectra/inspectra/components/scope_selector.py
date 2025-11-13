import reflex as rx

from inspectra.state.auth_state import AuthState
from inspectra.styles.global_styles import DS


def ScopeSelector():
    return rx.cond(
        AuthState.logged_in,
        rx.hstack(
            rx.select.root(
                rx.select.trigger(placeholder="Plant", style={"width": "120px", "min_width": "120px"}),
                rx.select.content(
                    rx.select.item(
                        "Plant: All",
                        value="all",
                        _hover={"background": DS.color.background, "color": DS.color.text_primary, "cursor": "pointer"},
                    ),
                    rx.foreach(
                        AuthState.plants,
                        lambda item: rx.select.item(
                            f"Plant: {item['name']}",
                            value=item["id"],
                            _hover={
                                "background": DS.color.background,
                                "color": DS.color.text_primary,
                                "cursor": "pointer",
                            },
                        ),
                    ),
                ),
                value=AuthState.selected_plant,
                on_change=AuthState.change_plant,
            ),
            rx.select.root(
                rx.select.trigger(placeholder="Line", style={"width": "120px", "min_width": "120px"}),
                rx.select.content(
                    rx.foreach(
                        AuthState.lines,
                        lambda item: rx.select.item(
                            f"Line: {item['name']}",
                            value=item["id"],
                            _hover={
                                "background": DS.color.background,
                                "color": DS.color.text_primary,
                                "cursor": "pointer",
                            },
                        ),
                    ),
                ),
                value=AuthState.selected_line,
                on_change=AuthState.change_line,
            ),
            align="center",
            spacing="2",
            on_mount=AuthState.fetch_line_scope,
        ),
        rx.fragment(),
    )
