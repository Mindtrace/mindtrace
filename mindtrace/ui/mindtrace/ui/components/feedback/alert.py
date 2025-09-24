from typing import Literal

import reflex as rx


class _AlertState(rx.State):
    """
    Internal per-alert state keyed by `cid`.

    Attributes:
        dismissed (dict[str, bool]): Whether a given alert (by `cid`) is dismissed.
    """

    dismissed: dict[str, bool] = {}

    def dismiss(self, cid: str) -> None:
        """
        Dismiss the alert for the given ID.

        Args:
            cid (str): Alert identifier.
        """
        self.dismissed[cid] = True

    def reset(self, cid: str) -> None:
        """
        Reset (show) the alert for the given ID.

        Args:
            cid (str): Alert identifier.
        """
        self.dismissed[cid] = False


def alert(
    message: str,
    severity: Literal["success", "error", "warning", "info"] = "info",
    dismissible: bool = True,
    cid: str = "default",
) -> rx.Component:
    """
    Render a dismissible alert banner with per-instance state via `cid`.

    Args:
        message (str): Alert text to display.
        severity (Literal["success","error","warning","info"], optional):
            Visual style of the alert. Defaults to "info".
        dismissible (bool, optional): If True, shows a close button. Defaults to True.
        cid (str, optional): Unique alert identifier for storing dismissed state. Defaults to "default".

    Returns:
        rx.Component: A styled Reflex alert component.
    """
    colors = {
        "success": ("#065f46", "rgba(16,185,129,.1)", "rgba(16,185,129,.3)"),
        "error": ("#991b1b", "rgba(239,68,68,.1)", "rgba(239,68,68,.3)"),
        "warning": ("#92400e", "rgba(245,158,11,.1)", "rgba(245,158,11,.3)"),
        "info": ("#1e40af", "rgba(59,130,246,.1)", "rgba(59,130,246,.3)"),
    }
    fg, bg, bd = colors.get(severity, colors["info"])

    return rx.cond(
        not _AlertState.dismissed.get(cid, False),
        rx.box(
            rx.hstack(
                rx.text(message, color=fg, size="3"),
                rx.spacer(),
                rx.cond(
                    dismissible,
                    rx.icon_button(
                        rx.icon(tag="x"),
                        on_click=lambda: _AlertState.dismiss(cid),
                        variant="ghost",
                    ),
                ),
                align="center",
                width="100%",
            ),
            background=bg,
            border=f"1px solid {bd}",
            border_radius="10px",
            padding="0.75rem",
        ),
        rx.fragment(),
    )
