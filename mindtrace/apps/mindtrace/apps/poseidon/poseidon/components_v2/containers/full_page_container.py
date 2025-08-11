import reflex as rx
from poseidon.styles.global_styles import COLORS, SIZING
from poseidon.components_v2.layout import basic_ease_in_background


def full_page_container(children, **kwargs) -> rx.Component:
    """
    Main page layout with background and container.
    """
    return rx.box(
        basic_ease_in_background(),
        rx.container(
            rx.box(
                *children,
                width="100%",
                padding=SIZING["container_padding"],
            ),
            center_content=True,
            style={
                "min_height": "100vh",
                "display": "flex",
                "align_items": "center",
                "justify_content": "center",
                "padding": "1.5rem 0",
            }
        ),
        style={
            "min_height": "100vh",
            "background": COLORS["background_primary"],
            "width": "100%",
            "position": "relative",
        },
        **kwargs
    )