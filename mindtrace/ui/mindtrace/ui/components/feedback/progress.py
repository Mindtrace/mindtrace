import reflex as rx


class _ProgressState(rx.State):
    """
    Internal state for progress components.

    Attributes:
        values (dict[str, int]): Mapping of component IDs (`cid`) to progress values (0–100).
    """

    values: dict[str, int] = {}

    def set(self, cid: str, v: int) -> None:
        """
        Set the progress value for a given component.

        Clamps the value to the range 0–100.

        Args:
            cid (str): Component identifier.
            v (int): Desired progress percentage.
        """
        self.values[cid] = max(0, min(100, int(v)))

    def inc(self, cid: str, step: int = 5) -> None:
        """
        Increase the progress value by a step.

        Args:
            cid (str): Component identifier.
            step (int, optional): Increment step. Defaults to 5.
        """
        self.set(cid, self.values.get(cid, 0) + step)

    def dec(self, cid: str, step: int = 5) -> None:
        """
        Decrease the progress value by a step.

        Args:
            cid (str): Component identifier.
            step (int, optional): Decrement step. Defaults to 5.
        """
        self.set(cid, self.values.get(cid, 0) - step)


def progress(cid: str = "default", show_label: bool = True) -> rx.Component:
    """
    Render a horizontal progress bar.

    Args:
        cid (str, optional): Component identifier used to read state. Defaults to "default".
        show_label (bool, optional): If True, shows a percentage label below the bar. Defaults to True.

    Returns:
        rx.Component: A styled Reflex progress component.
    """
    val = _ProgressState.values.get(cid, 0)
    return rx.vstack(
        rx.box(
            rx.box(width=f"{val}%", height="8px", background="#0057FF", border_radius="999px"),
            width="100%",
            height="8px",
            background="#e2e8f0",
            border_radius="999px",
            overflow="hidden",
        ),
        rx.cond(show_label, rx.text(f"{val}%", size="2", color="#64748b")),
        spacing="2",
        width="100%",
    )


def progress_controls(cid: str = "default") -> rx.Component:
    """
    Render simple controls to adjust a progress bar.

    Includes decrement, increment, and reset actions bound to the same `cid`.

    Args:
        cid (str, optional): Component identifier shared with the progress bar. Defaults to "default".

    Returns:
        rx.Component: A horizontal stack of buttons controlling progress state.
    """
    return rx.hstack(
        rx.button("−", on_click=lambda: _ProgressState.dec(cid)),
        rx.button("+", on_click=lambda: _ProgressState.inc(cid)),
        rx.button("Reset", on_click=lambda: _ProgressState.set(cid, 0)),
        spacing="2",
    )
