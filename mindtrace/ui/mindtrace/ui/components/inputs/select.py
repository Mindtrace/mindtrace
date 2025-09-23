from typing import Callable, Iterable, Union

import reflex as rx


class _SelectState(rx.State):
    """
    Internal state for select components.

    Attributes:
        values (dict[str, str]): Mapping of component IDs (`cid`) to the current selected value.
    """
    values: dict[str, str] = {}

    def set(self, cid: str, v: str) -> None:
        """
        Update the selected value for a given component.

        Args:
            cid (str): Select component identifier.
            v (str): New selected value.
        """
        self.values[cid] = v


def select(
    items: Iterable[Union[str, dict]],
    placeholder: str = "Select…",
    cid: str = "default",
    on_change: Callable[[str], None] | None = None,
) -> rx.Component:
    """
    Render a select input with per-`cid` internal state.

    Accepts either a list of strings or a list of dictionaries with the shape
    `{"label": str, "value": str}`. Strings are normalized into `{label, value}` pairs.

    Args:
        items (Iterable[Union[str, dict]]): Options to display. Each item is either
            a string or a dict with keys `"label"` and `"value"`.
        placeholder (str, optional): Placeholder text shown when no value is selected.
            Defaults to "Select…".
        cid (str, optional): Select component identifier for tracking state. Defaults to "default".
        on_change (Callable[[str], None] | None, optional): Optional callback invoked with
            the new value when selection changes. Defaults to None.

    Returns:
        rx.Component: A Reflex select component.
    """
    # Normalize items into {label, value} pairs.
    norm: list[dict[str, str]] = []
    for it in items:
        if isinstance(it, dict):
            norm.append(
                {
                    "label": it.get("label", it.get("value", "")),
                    "value": it.get("value", ""),
                }
            )
        else:
            s = str(it)
            norm.append({"label": s, "value": s})

    value = _SelectState.values.get(cid, "")

    return rx.select.root(
        rx.select.trigger(placeholder=placeholder),
        rx.select.content(
            *[rx.select.item(i["label"], value=i["value"]) for i in norm]
        ),
        value=value,
        on_change=lambda v: (
            _SelectState.set(cid, v),
            on_change(v) if on_change else None,
        ),
    )
