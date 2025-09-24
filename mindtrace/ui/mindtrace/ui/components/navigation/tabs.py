from typing import Any, Dict, List, Optional

import reflex as rx


class _TabsState(rx.State):
    """
    Internal state for horizontal tabs.

    Attributes:
        values (dict[str, str]): Mapping of tab group IDs (`cid`) to the currently selected value.
    """

    values: dict[str, str] = {}

    def set_value(self, cid: str, v: str) -> None:
        """
        Set the selected tab value for a given tab group.

        Args:
            cid (str): Tabs component identifier.
            v (str): Tab value to select.
        """
        self.values[cid] = v


def tabs(
    items: List[Dict[str, Any]],
    default_value: Optional[str] = None,
    cid: str = "default",
) -> rx.Component:
    """
    Render horizontal tabs with internal selected value per `cid`.

    Each `items` entry supports:
        - "label" (str): Text label for the tab.
        - "value" (str): Unique value for the tab (used for selection).
        - "content" (rx.Component): Content to render when this tab is active.
        - "icon" (str, optional): Optional icon text shown before the label.

    Args:
        items (list[dict]): List of tab definitions (see keys above).
        default_value (str, optional): Initial selected value. Defaults to the first item's value.
        cid (str, optional): Tabs identifier used to persist selection per instance. Defaults to "default".

    Returns:
        rx.Component: A Reflex tabs component.
    """
    if not items:
        return rx.box(rx.text("No tabs"))

    initial = default_value or items[0]["value"]
    value = _TabsState.values.get(cid, initial)

    return rx.tabs.root(
        rx.hstack(
            rx.tabs.list(
                *[
                    rx.tabs.trigger(
                        rx.hstack(
                            rx.text(tab.get("icon", ""), margin_right="6px") if tab.get("icon") else rx.fragment(),
                            rx.text(tab["label"]),
                            align="center",
                            spacing="1",
                        ),
                        value=tab["value"],
                        style={"cursor": "pointer"},
                    )
                    for tab in items
                ],
                style={
                    "background": "#fbfdff",
                    "border": "1px solid #e2e8f0",
                    "border_radius": "10px",
                    "padding": "6px",
                    "gap": "6px",
                },
            ),
            width="100%",
        ),
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
        value=value,
        on_change=lambda v: _TabsState.set_value(cid, v),
    )
