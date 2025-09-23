import reflex as rx


class _ToggleState(rx.State):
    """
    Internal state for toggle components.

    Attributes:
        values (dict[str, bool]): Mapping of component IDs (`cid`) to boolean values.
    """
    values: dict[str, bool] = {}

    def toggle(self, cid: str) -> None:
        """
        Flip the toggle state for a given component.

        Args:
            cid (str): Toggle component identifier.
        """
        self.values[cid] = not self.values.get(cid, False)


def toggle(label: str = "Toggle", cid: str = "default") -> rx.Component:
    """
    Render a boolean switch with internal state.

    Args:
        label (str, optional): Label text displayed alongside the toggle. Defaults to "Toggle".
        cid (str, optional): Toggle component identifier. Defaults to "default".

    Returns:
        rx.Component: A Reflex toggle switch with a label reflecting its state.
    """
    checked = _ToggleState.values.get(cid, False)
    return rx.hstack(
        rx.switch(
            checked=checked,
            on_change=lambda _: _ToggleState.toggle(cid),
        ),
        rx.text(f"{label}: {'On' if checked else 'Off'}", color="#64748b"),
        align="center",
        spacing="2",
    )
