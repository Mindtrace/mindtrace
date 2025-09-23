import reflex as rx


def badge(
    text: str,
    color: str = "#0f172a",
    background: str = "rgba(15,23,42,.06)",
) -> rx.Component:
    """
    Render a pill-style badge label.

    Useful for status indicators, tags, or small highlighted labels.

    Args:
        text (str): Text content displayed inside the badge.
        color (str, optional): Text color. Defaults to "#0f172a".
        background (str, optional): Background color. Defaults to "rgba(15,23,42,.06)".

    Returns:
        rx.Component: A styled Reflex badge component.
    """
    return rx.box(
        rx.text(text, size="2", color=color, weight="medium"),
        padding="0.25rem 0.5rem",
        border_radius="999px",
        background=background,
        display="inline-flex",
        align_items="center",
        justify_content="center",
    )
