import reflex as rx


def empty_state(
    icon: str = "📦",
    title: str = "Nothing here yet",
    description: str = "Start by creating your first item.",
    action_label: str | None = None,
    on_action=None,
    width: str = "100%",
) -> rx.Component:
    """
    Create a reusable empty state component.

    Displays an icon, a title, a description, and an optional action button.

    Args:
        icon (str, optional): Emoji or symbol to display at the top. Defaults to "📦".
        title (str, optional): Heading text. Defaults to "Nothing here yet".
        description (str, optional): Supporting description text. Defaults to "Start by creating your first item.".
        action_label (str | None, optional): Label for an optional action button. If None, no button is shown. Defaults to None.
        on_action (callable, optional): Function to call when the action button is clicked. Defaults to None.
        width (str, optional): CSS width of the component. Defaults to "100%".

    Returns:
        rx.Component: A styled Reflex component representing an empty state.
    """
    return rx.center(
        rx.vstack(
            rx.text(icon, font_size="2rem"),
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
        border="1px dashed #e2e8f0",
        border_radius="12px",
        background="#ffffff",
        width=width,
    )
