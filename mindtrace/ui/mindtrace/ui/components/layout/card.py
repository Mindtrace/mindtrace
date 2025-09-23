from typing import Sequence, Union

import reflex as rx


def card(
    children: Union[rx.Component, Sequence[rx.Component]],
    padding: str = "1rem",
    radius: str = "12px",
    border: str = "1px solid #e2e8f0",
    background: str = "white",
) -> rx.Component:
    """
    Render a simple elevated container (card).

    Args:
        children (rx.Component | Sequence[rx.Component]): One or more Reflex components to render inside the card.
        padding (str, optional): CSS padding. Defaults to "1rem".
        radius (str, optional): CSS border radius. Defaults to "12px".
        border (str, optional): CSS border style. Defaults to "1px solid #e2e8f0".
        background (str, optional): Background color. Defaults to "white".

    Returns:
        rx.Component: A styled Reflex card container.
    """
    if not isinstance(children, (list, tuple)):
        children = [children]
    return rx.box(
        *children,
        padding=padding,
        border_radius=radius,
        border=border,
        background=background,
        box_shadow="0 2px 10px rgba(15,23,42,.06)",
        width="100%",
    )
