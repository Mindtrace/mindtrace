# mindtrace/ui/mindtrace/ui/components/feedback/inline_alert.py
from typing import Literal

import reflex as rx


class _AlertState(rx.State):
    """
    Internal state manager for inline alerts.

    Tracks open/closed state per alert ID (`cid`).

    Attributes:
        open (dict[str, bool]): Mapping of alert IDs to open/closed states.
    """

    open: dict[str, bool] = {}

    def _set_open(self, cid: str, val: bool) -> None:
        """
        Set the open state of a given alert.

        Args:
            cid (str): Alert identifier.
            val (bool): Whether the alert should be open (True) or closed (False).
        """
        # Reflex requires clone -> mutate -> reassign
        data = dict(self.open or {})
        data[cid] = val
        self.open = data

    def close(self, cid: str) -> None:
        """
        Close (hide) the alert for a given ID.

        Args:
            cid (str): Alert identifier.
        """
        self._set_open(cid, False)

    def show(self, cid: str) -> None:
        """
        Show the alert for a given ID.

        Args:
            cid (str): Alert identifier.
        """
        self._set_open(cid, True)


def inline_alert(
    message: str,
    variant: Literal["info", "success", "warning", "error"] = "info",
    dismissible: bool = True,
    cid: str = "alert-1",
) -> rx.Component:
    """
    Render an inline alert component.

    Alerts are open by default unless explicitly dismissed in state.
    Supports multiple variants with different colors and styles.

    Args:
        message (str): Text message to display inside the alert.
        variant (Literal["info", "success", "warning", "error"], optional):
            Visual style of the alert. Defaults to "info".
        dismissible (bool, optional): If True, displays a close button. Defaults to True.
        cid (str, optional): Unique alert identifier used for per-instance state. Defaults to "alert-1".

    Returns:
        rx.Component: A styled Reflex inline alert component.
    """
    is_open = _AlertState.open.get(cid, True)

    # Variant styles
    bg = rx.cond(
        variant == "success",
        "rgba(16,185,129,0.10)",
        rx.cond(
            variant == "warning",
            "rgba(245,158,11,0.10)",
            rx.cond(
                variant == "error",
                "rgba(239,68,68,0.10)",
                "rgba(59,130,246,0.10)",  # info
            ),
        ),
    )
    border = rx.cond(
        variant == "success",
        "1px solid rgba(16,185,129,0.30)",
        rx.cond(
            variant == "warning",
            "1px solid rgba(245,158,11,0.30)",
            rx.cond(
                variant == "error",
                "1px solid rgba(239,68,68,0.30)",
                "1px solid rgba(59,130,246,0.30)",
            ),
        ),
    )
    color = rx.cond(
        variant == "success",
        "#065f46",
        rx.cond(
            variant == "warning",
            "#92400e",
            rx.cond(
                variant == "error",
                "#991b1b",
                "#1e40af",  # info
            ),
        ),
    )

    close_btn = rx.cond(
        dismissible,
        rx.icon_button(
            rx.icon(tag="x"),
            variant="ghost",
            size="1",
            on_click=lambda: _AlertState.close(cid),
            title="Dismiss",
            aria_label="Dismiss alert",
        ),
        rx.fragment(),
    )

    return rx.cond(
        is_open,
        rx.box(
            rx.hstack(
                rx.text(message, size="2", color=color),
                rx.spacer(),
                close_btn,
                align="center",
                width="100%",
            ),
            padding="0.75rem",
            border_radius="10px",
            background=bg,
            border=border,
            width="100%",
        ),
        rx.fragment(),
    )
