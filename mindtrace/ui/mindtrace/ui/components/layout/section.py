import reflex as rx
from typing import Optional


def section(
    title: str,
    description: str = "",
    content: Optional[rx.Component] = None,
) -> rx.Component:
    """
    Render a layout section with a heading, optional description, and content area.

    Args:
        title (str): Section heading text.
        description (str, optional): Supporting text shown under the heading.
            If empty, it is omitted. Defaults to "".
        content (rx.Component | None, optional): Body content to render beneath the header.
            If None, no content block is shown. Defaults to None.

    Returns:
        rx.Component: A vertical stack containing the section header and content.
    """
    return rx.vstack(
        rx.vstack(
            rx.heading(title, size="5", weight="bold", color="#0f172a"),
            rx.cond(
                description != "",
                rx.text(description, size="3", color="#64748b"),
            ),
            spacing="1",
            align="start",
            width="100%",
        ),
        rx.box(content) if content is not None else rx.fragment(),
        spacing="3",
        width="100%",
    )
