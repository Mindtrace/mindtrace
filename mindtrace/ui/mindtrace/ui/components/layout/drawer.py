import reflex as rx
from typing import Optional


class _DrawerState(rx.State):
    """
    Internal state for drawer components.

    Attributes:
        open (dict[str, bool]): Mapping of drawer IDs (`cid`) to their open state.
    """
    open: dict[str, bool] = {}

    def set(self, cid: str, value: bool) -> None:
        """
        Set the open state for a drawer.

        Args:
            cid (str): Drawer identifier.
            value (bool): True to open, False to close.
        """
        self.open[cid] = value


def drawer(
    trigger_label: str = "Open Drawer",
    title: str = "Drawer",
    content: Optional[rx.Component] = None,
    side: str = "right",
    cid: str = "default",
) -> rx.Component:
    """
    Render a side drawer (built on `rx.dialog`).

    Args:
        trigger_label (str, optional): Label text for the trigger button. Defaults to "Open Drawer".
        title (str, optional): Drawer heading. Defaults to "Drawer".
        content (rx.Component | None, optional): Content inside the drawer. Defaults to simple text.
        side (str, optional): Drawer position, either "left" or "right". Defaults to "right".
        cid (str, optional): Drawer identifier used to track open state. Defaults to "default".

    Returns:
        rx.Component: A Reflex drawer component.
    """
    if content is None:
        content = rx.text("Drawer content")

    pos = {
        "right": {
            "right": "0",
            "top": "0",
            "height": "100%",
            "width": "360px",
            "border_left": "1px solid #e2e8f0",
        },
        "left": {
            "left": "0",
            "top": "0",
            "height": "100%",
            "width": "360px",
            "border_right": "1px solid #e2e8f0",
        },
    }.get(
        side,
        {"right": "0", "top": "0", "height": "100%", "width": "360px", "border_left": "1px solid #e2e8f0"},
    )

    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(trigger_label, on_click=lambda: _DrawerState.set(cid, True))
        ),
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.heading(title, size="4"),
                    rx.spacer(),
                    rx.dialog.close(
                        rx.icon_button(
                            rx.icon(tag="x"),
                            variant="ghost",
                            on_click=lambda: _DrawerState.set(cid, False),
                        )
                    ),
                    align="center",
                    width="100%",
                ),
                rx.box(content, width="100%"),
                spacing="4",
                width="100%",
                height="100%",
            ),
            position="fixed",
            background="#fff",
            **pos,
        ),
        open=_DrawerState.open.get(cid, False),
        on_open_change=lambda o: _DrawerState.set(cid, o),
    )
