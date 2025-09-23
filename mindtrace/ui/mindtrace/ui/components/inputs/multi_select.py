import reflex as rx


class _MultiSelectState(rx.State):
    """
    Internal state for multi-select components.

    Attributes:
        values (dict[str, list[str]]): Mapping of component IDs (`cid`) to lists of selected values.
    """
    values: dict[str, list[str]] = {}

    def toggle(self, cid: str, value: str) -> None:
        """
        Toggle a value in the selection list for a given component.

        Args:
            cid (str): Multi-select identifier.
            value (str): Value to add or remove from the selection.
        """
        current = list(self.values.get(cid, []))
        if value in current:
            current = [v for v in current if v != value]
        else:
            current.append(value)
        self.values[cid] = current

    def clear(self, cid: str) -> None:
        """
        Clear all selected values for a given component.

        Args:
            cid (str): Multi-select identifier.
        """
        self.values[cid] = []


def _selected_chip(cid: str) -> rx.Component:
    """
    Render selected tags as removable chips.

    Uses `rx.foreach` to safely render the reactive list of selected values.

    Args:
        cid (str): Multi-select identifier.

    Returns:
        rx.Component: A horizontal stack of selected chips.
    """
    return rx.hstack(
        rx.foreach(
            _MultiSelectState.values.get(cid, []),
            lambda v: rx.box(
                rx.hstack(
                    rx.text(v),
                    rx.text(
                        "×",
                        cursor="pointer",
                        on_click=lambda _v=v: _MultiSelectState.toggle(cid, _v),
                    ),
                    spacing="1",
                    align="center",
                ),
                padding="2px 8px",
                border_radius="999px",
                background="#ecfeff",
                color="#0e7490",
            ),
        ),
        spacing="2",
        wrap="wrap",
    )


def _options_list(options: list[str], cid: str) -> rx.Component:
    """
    Render the list of selectable options.

    Each option is a button that toggles its selection.  
    Styling is kept static to avoid reactive `in` checks.

    Args:
        options (list[str]): List of available options.
        cid (str): Multi-select identifier.

    Returns:
        rx.Component: A vertical stack of option buttons.
    """
    return rx.vstack(
        *[
            rx.button(
                option,
                size="2",
                variant="surface",
                on_click=lambda _o=option: _MultiSelectState.toggle(cid, _o),
                width="100%",
                justify="start",
            )
            for option in options
        ],
        spacing="2",
        width="100%",
    )


def multi_select(options: list[str], cid: str = "ms1") -> rx.Component:
    """
    Render a minimal, state-driven multi-select component.

    Features:
        - Selected values shown as removable chips (using `_selected_chip`).
        - Options displayed as buttons (non-reactive styling).
        - Selected count shown with `.length()` on the reactive Var.

    Args:
        options (list[str]): List of selectable options.
        cid (str, optional): Multi-select identifier. Defaults to "ms1".

    Returns:
        rx.Component: A styled Reflex multi-select component.
    """
    return rx.vstack(
        rx.box(
            _selected_chip(cid),
            border="1px solid #e2e8f0",
            border_radius="10px",
            padding="8px",
            background="#fff",
            width="100%",
        ),
        rx.hstack(
            rx.text("Selected:"),
            rx.text(_MultiSelectState.values.get(cid, []).length()),
            rx.spacer(),
            rx.button(
                "Clear",
                size="1",
                variant="ghost",
                on_click=lambda: _MultiSelectState.clear(cid),
            ),
            width="100%",
            align="center",
        ),
        _options_list(options, cid),
        spacing="3",
        width="100%",
    )
