# mindtrace/ui/mindtrace/ui/components/overlay/confirm.py
from typing import Callable, Literal

import reflex as rx


class _ConfirmState(rx.State):
    """
    Internal open/close state for confirm dialogs, keyed by `cid`.

    Attributes:
        open (dict[str, bool]): Mapping of dialog IDs (`cid`) to their open state.
    """
    open: dict[str, bool] = {}

    def set(self, cid: str, val: bool) -> None:
        """
        Set the open state for a given dialog.

        Args:
            cid (str): Dialog identifier.
            val (bool): True to open, False to close.
        """
        self.open[cid] = val


def confirm(
    trigger_label: str = "Delete",
    title: str = "Confirm action",
    message: str = "Are you sure?",
    confirm_label: str = "Confirm",
    on_confirm: Callable[[], None] | None = None,
    cid: str = "default",
    variant: Literal["danger", "default"] = "danger",
) -> rx.Component:
    """
    Render a confirm dialog with a trigger button.

    Clicking the trigger opens a modal dialog with a title, message, and
    Cancel/Confirm actions. Confirm invokes `on_confirm` (if provided) and
    always closes the dialog.

    Args:
        trigger_label (str, optional): Text for the trigger button. Defaults to "Delete".
        title (str, optional): Dialog title. Defaults to "Confirm action".
        message (str, optional): Dialog body text. Defaults to "Are you sure?".
        confirm_label (str, optional): Text for the confirm button. Defaults to "Confirm".
        on_confirm (Callable[[], None] | None, optional): Callback executed upon confirmation. Defaults to None.
        cid (str, optional): Dialog identifier used to manage open state. Defaults to "default".
        variant (Literal["danger","default"], optional): Visual style for the trigger button. Defaults to "danger".

    Returns:
        rx.Component: A Reflex dialog component wired to internal state.
    """
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                trigger_label,
                variant="solid" if variant == "danger" else "outline",
                on_click=lambda: _ConfirmState.set(cid, True),
            )
        ),
        rx.dialog.content(
            rx.vstack(
                rx.heading(title, size="4"),
                rx.text(message, size="2", color="#64748b"),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="ghost",
                            on_click=lambda: _ConfirmState.set(cid, False),
                        )
                    ),
                    rx.button(
                        confirm_label,
                        variant="solid",
                        on_click=lambda: (
                            _ConfirmState.set(cid, False),
                            on_confirm() if on_confirm else None
                        ),
                    ),
                    justify="end",
                    width="100%",
                    spacing="2",
                ),
                spacing="3",
                width="100%",
            )
        ),
        open=_ConfirmState.open.get(cid, False),
        on_open_change=lambda o: _ConfirmState.set(cid, o),
    )
