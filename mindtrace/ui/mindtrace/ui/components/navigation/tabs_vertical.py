import reflex as rx
from typing import Any, Dict, List, Optional


class _VTabState(rx.State):
    """
    Internal state for vertical tabs.

    Attributes:
        values (dict[str, str]): Mapping of tab IDs (`cid`) to currently selected value.
    """
    values: dict[str, str] = {}

    def set_value(self, cid: str, v: str) -> None:
        """
        Set the selected tab value for a given component.

        Args:
            cid (str): Tabs component identifier.
            v (str): Tab value to select.
        """
        self.values[cid] = v


def vertical_tabs(
    items: List[Dict[str, Any]],
    default_value: Optional[str] = None,
    cid: str = "default",
    width: str = "100%",
) -> rx.Component:
    """
    Render a vertical tabs component.

    Each item dict must include:
        - "label" (str): Tab label.
        - "value" (str): Unique tab identifier.
        - "content" (rx.Component): Content to display when the tab is active.

    Args:
        items (list[dict]): List of tab definitions.
        default_value (str, optional): Initial selected value. Defaults to first item's value.
        cid (str, optional): Component identifier for tracking state. Defaults to "default".
        width (str, optional): CSS width of the entire tabs container. Defaults to "100%".

    Returns:
        rx.Component: A styled vertical tabs component.
    """
    if not items:
        return rx.box(rx.text("No tabs"))

    initial = default_value or items[0]["value"]
    value = _VTabState.values.get(cid, initial)

    return rx.tabs.root(
        rx.hstack(
            rx.tabs.list(
                *[
                    rx.tabs.trigger(
                        tab["label"],
                        value=tab["value"],
                        style={"cursor": "pointer"},
                    )
                    for tab in items
                ],
                orientation="vertical",
                style={
                    "min_width": "180px",
                    "background": "#fbfdff",
                    "border": "1px solid #e2e8f0",
                    "border_radius": "10px",
                    "padding": "6px",
                    "gap": "6px",
                },
            ),
            rx.box(
                *[
                    rx.tabs.content(
                        rx.box(
                            tab["content"],
                            padding="1rem",
                            border="1px solid #e2e8f0",
                            border_radius="10px",
                            background="#fff",
                        ),
                        value=tab["value"],
                    )
                    for tab in items
                ],
                flex="1",
            ),
            spacing="4",
            width=width,
            align="start",
        ),
        value=value,
        on_change=lambda v: _VTabState.set_value(cid, v),
        orientation="vertical",
        style={"width": width},
    )
