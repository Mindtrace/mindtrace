import reflex as rx
from typing import Callable


def empty_table(
    title: str = "No data",
    description: str = "There are no rows to display.",
    action_label: str | None = None,
    on_action: Callable[[], None] | None = None,
) -> rx.Component:
    """
    Create an empty table state component.

    Displays an icon, a title, a description, and an optional action button
    when there are no rows to show in a table.

    Args:
        title (str, optional): Heading text. Defaults to "No data".
        description (str, optional): Supporting description text. Defaults to "There are no rows to display.".
        action_label (str | None, optional): Label for an optional action button. If None, no button is shown. Defaults to None.
        on_action (Callable[[], None] | None, optional): Function to call when the action button is clicked. Defaults to None.

    Returns:
        rx.Component: A styled Reflex component representing an empty table state.
    """
    return rx.box(
        rx.vstack(
            rx.text("📭", font_size="2rem"),
            rx.heading(title, size="4"),
            rx.text(description, size="2", color="#64748b", text_align="center"),
            rx.cond(
                action_label is not None,
                rx.button(action_label, on_click=on_action),
            ),
            spacing="3",
            align="center",
        ),
        padding="2rem",
        width="100%",
        background="#fff",
        border="1px dashed #e2e8f0",
        border_radius="12px",
    )
