from typing import Callable

import reflex as rx


class _TextState(rx.State):
    """
    Internal state for text-based input components.

    Attributes:
        values (dict[str, str]): Mapping of component IDs (`cid`) to their current text value.
    """
    values: dict[str, str] = {}

    def set_value(self, cid: str, v: str) -> None:
        """
        Update the stored value for a given input.

        Args:
            cid (str): Input identifier.
            v (str): New text value.
        """
        self.values[cid] = v


def input_with_label(
    label: str,
    placeholder: str = "Type…",
    cid: str = "default",
    on_change: Callable[[str], None] | None = None,
) -> rx.Component:
    """
    Render a labeled text input.

    Value is tracked in `_TextState` keyed by `cid`.

    Args:
        label (str): Label text displayed above the input field.
        placeholder (str, optional): Input placeholder text. Defaults to "Type…".
        cid (str, optional): Input identifier for state tracking. Defaults to "default".
        on_change (Callable[[str], None] | None, optional): Optional callback called with
            the new value on change. Defaults to None.

    Returns:
        rx.Component: A styled Reflex input with label.
    """
    value = _TextState.values.get(cid, "")
    return rx.vstack(
        rx.text(label, size="2", color="#64748b"),
        rx.input(
            value=value,
            on_change=lambda v: (
                _TextState.set_value(cid, v),
                on_change(v) if on_change else None,
            ),
            placeholder=placeholder,
            border="1px solid #e2e8f0",
            border_radius="10px",
            padding="0.6rem 0.8rem",
            width="100%",
        ),
        spacing="1",
        width="100%",
    )


def search_input(
    placeholder: str = "Search…",
    button_label: str = "Search",
    on_search: Callable[[str], None] | None = None,
    cid: str = "default",
) -> rx.Component:
    """
    Render a search input with a button.

    Value is tracked in `_TextState` keyed by `cid`. Pressing the button triggers
    `on_search` with the current value.

    Args:
        placeholder (str, optional): Input placeholder text. Defaults to "Search…".
        button_label (str, optional): Label for the search button. Defaults to "Search".
        on_search (Callable[[str], None] | None, optional): Callback executed when the search
            button is clicked, with the current value passed as argument. Defaults to None.
        cid (str, optional): Input identifier for state tracking. Defaults to "default".

    Returns:
        rx.Component: A styled Reflex search input with button.
    """
    value = _TextState.values.get(cid, "")
    return rx.hstack(
        rx.input(
            value=value,
            on_change=lambda v: _TextState.set_value(cid, v),
            placeholder=placeholder,
            border="1px solid #e2e8f0",
            border_radius="10px",
            padding="0.6rem 0.8rem",
            width="100%",
        ),
        rx.button(
            button_label,
            on_click=lambda: (
                on_search(_TextState.values.get(cid, "")) if on_search else None
            ),
        ),
        align="center",
        spacing="3",
        width="100%",
    )
