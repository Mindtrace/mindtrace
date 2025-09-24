from typing import Any, Dict, List, Optional

import reflex as rx


class _PillTabsState(rx.State):
    """
    Internal state for pill-style tabs, keyed by component ID (`cid`).

    Attributes:
        selected_by_cid (dict[str, str]): Mapping of `cid` to the currently selected tab value.
    """

    selected_by_cid: dict[str, str] = {}

    def select_value(self, cid: str, value: str) -> None:
        """
        Select a tab value for a given component.

        Args:
            cid (str): Tabs component identifier.
            value (str): Tab value to select.
        """
        cur = dict(self.selected_by_cid)
        cur[cid] = value
        self.selected_by_cid = cur


def pill_tabs(
    tabs: List[Dict[str, Any]],
    cid: str = "pilltabs-1",
) -> rx.Component:
    """
    Render pill-style tabs with optional badges and content panels.

    Each tab dict supports:
        - "label" (str): User-facing label.
        - "value" (str): Unique value for the tab (used for selection).
        - "content" (rx.Component): Content to render when active.
        - "badge" (int | None, optional): Optional badge count displayed next to the label.

    Args:
        tabs (list[dict]): List of tab definitions (see keys above).
        cid (str, optional): Stable component ID used to persist selection per instance.
            Defaults to "pilltabs-1".

    Returns:
        rx.Component: A Reflex tabs component styled as pills.
    """
    if not tabs:
        return rx.box(rx.text("No tabs"), padding="1rem")

    default_value = tabs[0].get("value", "tab-1")

    triggers = []
    for t in tabs:
        label: str = t.get("label", t.get("value", ""))
        badge: Optional[int] = t.get("badge")

        trigger_child = rx.hstack(
            rx.text(label),
            rx.cond(
                badge is not None,
                rx.badge(str(badge), size="1"),
                rx.fragment(),
            ),
            spacing="2",
            align="center",
        )

        triggers.append(
            rx.tabs.trigger(
                trigger_child,
                value=t["value"],
                style={
                    "border_radius": "999px",
                    "padding": "6px 12px",
                    "border": "1px solid #e2e8f0",
                },
            )
        )

    contents = [
        rx.tabs.content(
            t.get("content", rx.text(f"{t.get('label', t['value'])} content")),
            value=t["value"],
            style={
                "padding": "1rem",
                "border": "1px solid #e2e8f0",
                "border_radius": "12px",
                "background": "#ffffff",
            },
        )
        for t in tabs
    ]

    return rx.tabs.root(
        rx.vstack(
            rx.tabs.list(
                *triggers,
                style={
                    "display": "flex",
                    "gap": "8px",
                    "flex_wrap": "wrap",
                    "background": "#f8fafc",
                    "padding": "8px",
                    "border_radius": "12px",
                    "border": "1px solid #e2e8f0",
                },
            ),
            *contents,
            spacing="3",
            width="100%",
        ),
        value=_PillTabsState.selected_by_cid.get(cid, default_value),
        on_change=lambda v, _cid=cid: _PillTabsState.select_value(_cid, v),
    )
