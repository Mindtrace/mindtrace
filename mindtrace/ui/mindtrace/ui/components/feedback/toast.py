import reflex as rx
from typing import Literal


class _ToastState(rx.State):
    """
    Internal state manager for toast notifications.

    Attributes:
        toasts (dict[str, list[dict]]): Mapping of container IDs (`cid`) to lists of
            toast dictionaries. Each toast dict has:
            - id (str): Unique toast identifier.
            - message (str): Toast text content.
            - variant (str): Toast variant ("success", "error", "warning", "info").
    """
    toasts: dict[str, list[dict]] = {}

    def add(self, cid: str, message: str, variant: str = "info") -> None:
        """
        Add a new toast to a container.

        Args:
            cid (str): Container identifier.
            message (str): Text to display in the toast.
            variant (str, optional): Toast style. Defaults to "info".
        """
        stack = list(self.toasts.get(cid, []))
        stack.append({"id": self._gen_id(), "message": message, "variant": variant})
        self.toasts[cid] = stack

    def remove(self, cid: str, toast_id: str) -> None:
        """
        Remove a toast from a container.

        Args:
            cid (str): Container identifier.
            toast_id (str): Identifier of the toast to remove.
        """
        self.toasts[cid] = [t for t in self.toasts.get(cid, []) if t["id"] != toast_id]

    def clear(self, cid: str) -> None:
        """
        Remove all toasts from a container.

        Args:
            cid (str): Container identifier.
        """
        self.toasts[cid] = []

    def _gen_id(self) -> str:
        """
        Generate a unique toast identifier.

        Returns:
            str: Unique toast ID.
        """
        return f"t{len(self.toasts)}_{self.get_token()}"


def toast_portal(
    cid: str = "default",
    position: Literal["top-right", "top-left", "bottom-right", "bottom-left"] = "top-right",
) -> rx.Component:
    """
    Render a fixed-position toast container (portal).

    To trigger a toast, call: `_ToastState.add(cid, message, variant)`.

    Args:
        cid (str, optional): Container identifier. Defaults to "default".
        position (Literal["top-right","top-left","bottom-right","bottom-left"], optional):
            Position of the toast stack. Defaults to "top-right".

    Returns:
        rx.Component: A styled Reflex toast portal.
    """
    pos = {
        "top-right": {"top": "16px", "right": "16px"},
        "top-left": {"top": "16px", "left": "16px"},
        "bottom-right": {"bottom": "16px", "right": "16px"},
        "bottom-left": {"bottom": "16px", "left": "16px"},
    }.get(position, {"top": "16px", "right": "16px"})

    colors = {
        "success": ("#065f46", "rgba(16,185,129,.1)", "rgba(16,185,129,.3)"),
        "error":   ("#991b1b", "rgba(239,68,68,.1)", "rgba(239,68,68,.3)"),
        "warning": ("#92400e", "rgba(245,158,11,.1)", "rgba(245,158,11,.3)"),
        "info":    ("#1e40af", "rgba(59,130,246,.1)", "rgba(59,130,246,.3)"),
    }

    def toast_item(t: dict) -> rx.Component:
        fg, bg, bd = colors.get(t["variant"], colors["info"])
        return rx.box(
            rx.hstack(
                rx.text(t["message"], color=fg, size="3"),
                rx.spacer(),
                rx.icon_button(
                    rx.icon(tag="x"),
                    on_click=lambda tid=t["id"]: _ToastState.remove(cid, tid),
                    variant="ghost",
                ),
                align="center",
                width="100%",
            ),
            background=bg,
            border=f"1px solid {bd}",
            border_radius="10px",
            padding="0.75rem",
            width="320px",
        )

    return rx.box(
        rx.vstack(
            *[toast_item(t) for t in _ToastState.toasts.get(cid, [])[::-1]],
            spacing="2",
            align="stretch",
        ),
        position="fixed",
        z_index="1000",
        **pos,
    )


def trigger_toast_button(
    label: str = "Notify",
    message: str = "Hello!",
    variant: Literal["success", "error", "warning", "info"] = "info",
    cid: str = "default",
) -> rx.Component:
    """
    Render a button that triggers a toast when clicked.

    Args:
        label (str, optional): Button label. Defaults to "Notify".
        message (str, optional): Toast message text. Defaults to "Hello!".
        variant (Literal["success","error","warning","info"], optional):
            Toast style. Defaults to "info".
        cid (str, optional): Container identifier. Defaults to "default".

    Returns:
        rx.Component: A Reflex button bound to a toast trigger.
    """
    return rx.button(label, on_click=lambda: _ToastState.add(cid, message, variant))
