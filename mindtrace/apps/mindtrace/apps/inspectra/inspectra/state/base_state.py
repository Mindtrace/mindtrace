import reflex as rx

class BaseState(rx.State):
    """Base Reflex state with shared helpers."""

    def redirect(self, path: str):
        """Client-side redirect."""
        return rx.redirect(path)

    def notify(self, message: str, color: str = "green"):
        """Show a toast or notification."""
        return rx.toast(message, color=color)
