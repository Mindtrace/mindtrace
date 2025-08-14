import reflex as rx

from poseidon.components_v2.layout import basic_ease_in_background
from poseidon.styles.global_styles import THEME as T


def login_page_container(children, **kwargs) -> rx.Component:
    """
    Main page layout with background and container.
    Uses new token system.
    """
    return rx.box(
        basic_ease_in_background(),
        rx.container(
            rx.box(
                *children,
                width="100%",
                padding=f"0 {T.spacing.space_6}",
            ),
            center_content=True,
            style={
                "min_height": "100vh",
                "display": "flex",
                "align_items": "center",
                "justify_content": "center",
                "padding": f"{T.spacing.space_6} 0",
            },
        ),
        style={
            "min_height": "100vh",
            "width": "100%",
            "position": "relative",
        },
        **kwargs,
    )
