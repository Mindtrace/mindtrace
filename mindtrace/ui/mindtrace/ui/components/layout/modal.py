import reflex as rx
from typing import Callable, Optional


class _ModalState(rx.State):
    """
    Internal state for modal dialogs.

    Attributes:
        open (dict[str, bool]): Mapping of modal IDs (`cid`) to their open state.
    """
    open: dict[str, bool] = {}

    def set_open(self, cid: str, value: bool) -> None:
        """
        Set the open state for a given modal.

        Args:
            cid (str): Modal identifier.
            value (bool): True to open, False to close.
        """
        self.open[cid] = value


def modal(
    trigger_label: str = "Open",
    title: str = "Modal Title",
    body: Optional[rx.Component] = None,
    confirm_label: str = "Confirm",
    on_confirm: Callable[[], None] | None = None,
    cid: str = "default",
) -> rx.Component:
    """
    Render a modal dialog with trigger, title, body, and confirm/cancel actions.

    Args:
        trigger_label (str, optional): Label for the button that opens the modal. Defaults to "Open".
        title (str, optional): Title displayed at the top of the modal. Defaults to "Modal Title".
        body (rx.Component | None, optional): Content inside the modal body. Defaults to simple text.
        confirm_label (str, optional): Label for the confirm button. Defaults to "Confirm".
        on_confirm (Callable[[], None] | None, optional): Callback executed on confirmation. Defaults to None.
        cid (str, optional): Modal identifier for managing state. Defaults to "default".

    Returns:
        rx.Component: A styled Reflex modal component.
    """
    if body is None:
        body = rx.text("This is a modal body.")

    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(trigger_label, on_click=lambda: _ModalState.set_open(cid, True))
        ),
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.heading(title, size="4"),
                    rx.spacer(),
                    rx.dialog.close(
                        rx.icon_button(
                            rx.icon(tag="x"),
                            on_click=lambda: _ModalState.set_open(cid, False),
                            variant="ghost",
                        )
                    ),
                    align="center",
                    width="100%",
                ),
                body,
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="ghost",
                            on_click=lambda: _ModalState.set_open(cid, False),
                        )
                    ),
                    rx.button(
                        confirm_label,
                        variant="solid",
                        on_click=lambda: (
                            _ModalState.set_open(cid, False),
                            on_confirm() if on_confirm else None,
                        ),
                    ),
                    justify="end",
                    width="100%",
                    spacing="3",
                ),
                spacing="4",
                width="100%",
            ),
            max_width="540px",
        ),
        open=_ModalState.open.get(cid, False),
        on_open_change=lambda o: _ModalState.set_open(cid, o),
    )
