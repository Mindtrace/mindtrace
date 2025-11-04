import reflex as rx


class ShellState(rx.State):
    """App shell state."""

    @rx.var
    def current_path(self) -> str:
        return self.router.page.path or "/"

    @rx.var
    def is_public(self) -> bool:
        path = self.current_path
        return path.endswith("/login") or path.endswith("/forgot-password") or path == "/"
