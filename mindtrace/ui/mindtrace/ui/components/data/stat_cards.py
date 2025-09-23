import reflex as rx


def stat_card(title: str, value: str, subtitle: str = "", icon: str = "") -> rx.Component:
    """
    Create a single statistic card.

    Displays a title, main value, optional subtitle, and optional icon.

    Args:
        title (str): The label for the statistic.
        value (str): The primary value to display.
        subtitle (str, optional): An additional description or status (e.g., "Up 20%"). Defaults to "".
        icon (str, optional): Icon text or symbol to render on the right side. Defaults to "".

    Returns:
        rx.Component: A styled Reflex box containing the stat card.
    """
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(title, size="2", color="#64748b"),
                rx.spacer(),
                rx.cond(icon != "", rx.text(icon), rx.fragment()),
                align="center",
                width="100%",
            ),
            rx.text(value, size="6", weight="bold", color="#0f172a"),
            rx.cond(
                subtitle != "",
                rx.text(subtitle, size="2", color="#22c55e"),
                rx.fragment(),
            ),
            spacing="1",
            align_items="start",
            width="100%",
        ),
        padding="1rem",
        background="#ffffff",
        border="1px solid #e2e8f0",
        border_radius="12px",
        box_shadow="0 1px 2px rgba(15,23,42,.06)",
        width="100%",
    )


def stat_grid(cards) -> rx.Component:
    """
    Create a responsive grid of statistic cards.

    Each card is generated from a dictionary with keys:
    - "title" (str): Label for the stat.
    - "value" (str): Primary value.
    - "subtitle" (str): Optional detail text.
    - "icon" (str): Optional icon text.

    Args:
        cards (Iterable[dict]): A list or Reflex Var of dictionaries defining the stat cards.

    Returns:
        rx.Component: A responsive Reflex grid containing the stat cards.
    """
    return rx.grid(
        rx.foreach(
            cards,
            lambda c: stat_card(
                c["title"],
                c["value"],
                c["subtitle"],
                c["icon"],
            ),
        ),
        columns="1",
        gap="1rem",
        width="100%",
        style={
            "gridTemplateColumns": "repeat(auto-fill, minmax(240px, 1fr))",
        },
    )
