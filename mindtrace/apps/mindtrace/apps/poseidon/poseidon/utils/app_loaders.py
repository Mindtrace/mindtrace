# poseidon/utils/app_loaders.py
from typing import Callable, Iterable, Optional, List
import reflex as rx

from poseidon.components_v2.layout.appshell import AppShell
from poseidon.state.auth import AuthState

COOKIE_NAME = "auth_token"


# ---------- Shell wrappers ----------

def with_shell(
    body_fn: Callable[[], rx.Component],
    *,
    title: str,
    active: str,
    header_right_fn: Optional[Callable[[], rx.Component]] = None,
    subheader_fn: Optional[Callable[[], rx.Component]] = None,
    show_scope_selector: bool = False,
):
    """Standard app shell (sidebar/header). Use for *authenticated* pages."""
    def wrapped():
        return AppShell(
            title=title,
            sidebar_active=active,
            header_right=header_right_fn() if header_right_fn else None,
            subheader=subheader_fn() if subheader_fn else None,
            body=body_fn(),
            show_scope_selector=show_scope_selector,
        )
    return wrapped


def _cookie_gate_html() -> rx.Component:
    """Instant client-side redirect to /login if the auth cookie is absent."""
    return rx.html(
        f"<script>if(!document.cookie.match(/(?:^|; ){COOKIE_NAME}=/)){{location.replace('/login');}}</script>"
    )


def with_protected_shell(
    body_fn: Callable[[], rx.Component],
    *,
    title: str,
    active: str,
    header_right_fn: Optional[Callable[[], rx.Component]] = None,
    subheader_fn: Optional[Callable[[], rx.Component]] = None,
    show_scope_selector: bool = False,
):
    """
    Shell wrapper that injects a zero-latency client-side redirect when no cookie is present.
    Use for *authenticated* pages to avoid flicker before server on_load runs.
    """
    def wrapped():
        return rx.fragment(
            _cookie_gate_html(),  # runs before anything renders
            AppShell(
                title=title,
                sidebar_active=active,
                header_right=header_right_fn() if header_right_fn else None,
                subheader=subheader_fn() if subheader_fn else None,
                body=body_fn(),
                show_scope_selector=show_scope_selector,
            ),
        )
    return wrapped


def without_shell(body_fn: Callable[[], rx.Component]):
    """
    Minimal wrapper for *public* pages (e.g., /login, /register) that should NOT render the AppShell.
    """
    def wrapped():
        return body_fn()
    return wrapped


def _ensure_list(loaders: Optional[Iterable[Callable[[], object]]]) -> List[Callable[[], object]]:
    return list(loaders) if loaders else []


# ---------- Route helpers ----------

def add_public_page(
    app: rx.App,
    *,
    route: str,
    body_fn: Callable[[], rx.Component],
    title: str,
):
    """
    Public pages like /login, /register.
    - No AppShell (so they don't appear inside the dashboard).
    - If already authenticated, redirect to '/'.
    """
    app.add_page(
        without_shell(body_fn),   # <-- no AppShell here
        route=route,
        title=title,
        on_load=AuthState.redirect_if_authenticated,
    )


def add_protected_page(
    app: rx.App,
    *,
    route: str,
    body_fn: Callable[[], rx.Component],
    title: str,
    active: str,
    extra_on_load: Optional[Iterable[Callable[[], object]]] = None,
    header_right_fn: Optional[Callable[[], rx.Component]] = None,
    subheader_fn: Optional[Callable[[], rx.Component]] = None,
    show_scope_selector: bool = False,
):
    """
    Protected pages (auth required).
    - Render inside AppShell with a client-side cookie gate (instant).
    - Server on_load guard still runs for correctness (e.g., expired token).
    """
    loaders: List[Callable[[], object]] = [AuthState.redirect_if_not_authenticated]
    loaders += _ensure_list(extra_on_load)
    app.add_page(
        with_protected_shell(
            body_fn,
            title=title,
            active=active,
            header_right_fn=header_right_fn,
            subheader_fn=subheader_fn,
            show_scope_selector=show_scope_selector,
        ),
        route=route,
        title=title,
        on_load=loaders,  # list of State handlers
    )


def add_admin_page(
    app: rx.App,
    *,
    route: str,
    body_fn: Callable[[], rx.Component],
    title: str,
    active: str,
    extra_on_load: Optional[Iterable[Callable[[], object]]] = None,
    header_right_fn: Optional[Callable[[], rx.Component]] = None,
    subheader_fn: Optional[Callable[[], rx.Component]] = None,
    show_scope_selector: bool = False,
):
    """Org admin-only page (inside AppShell)."""
    loaders: List[Callable[[], object]] = [AuthState.redirect_if_not_admin]
    loaders += _ensure_list(extra_on_load)
    app.add_page(
        with_protected_shell(
            body_fn,
            title=title,
            active=active,
            header_right_fn=header_right_fn,
            subheader_fn=subheader_fn,
            show_scope_selector=show_scope_selector,
        ),
        route=route,
        title=title,
        on_load=loaders,
    )


def add_super_admin_page(
    app: rx.App,
    *,
    route: str,
    body_fn: Callable[[], rx.Component],
    title: str,
    active: str,
    extra_on_load: Optional[Iterable[Callable[[], object]]] = None,
    header_right_fn: Optional[Callable[[], rx.Component]] = None,
    subheader_fn: Optional[Callable[[], rx.Component]] = None,
    show_scope_selector: bool = False,
):
    """Super admin-only page (inside AppShell)."""
    loaders: List[Callable[[], object]] = [AuthState.redirect_if_not_super_admin]
    loaders += _ensure_list(extra_on_load)
    app.add_page(
        with_protected_shell(
            body_fn,
            title=title,
            active=active,
            header_right_fn=header_right_fn,
            subheader_fn=subheader_fn,
            show_scope_selector=show_scope_selector,
        ),
        route=route,
        title=title,
        on_load=loaders,
    )
