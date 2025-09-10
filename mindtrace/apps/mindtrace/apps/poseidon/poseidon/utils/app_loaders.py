from typing import Callable, Iterable, Optional
import reflex as rx

from poseidon.components_v2.layout.appshell import AppShell
from poseidon.state.auth import AuthState


def with_shell(body_fn, *, title, active,
               header_right_fn=None, subheader_fn=None, show_scope_selector=False):
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


def compose_loaders(*loaders: Callable[[], Optional[object]]) -> Callable[[], Optional[object]]:
    def _run():
        for fn in loaders:
            if not fn:
                continue
            res = fn()
            if res is not None:
                return res  # stop if a loader returns actions/redirect
    return _run


def add_public_page(app: rx.App, *, route: str, body_fn, title: str, active: str = "",
                    header_right_fn=None, subheader_fn=None, show_scope_selector=False):
    """Pages like /login, /register. If authed, redirect to '/'."""
    app.add_page(
        with_shell(
            body_fn,
            title=title,
            active=active,
            header_right_fn=header_right_fn,
            subheader_fn=subheader_fn,
            show_scope_selector=show_scope_selector,
        ),
        route=route,
        on_load=AuthState.redirect_if_authenticated,
    )


def add_protected_page(app: rx.App, *, route: str, body_fn, title: str, active: str,
                       extra_on_load: Optional[Iterable[Callable[[], Optional[object]]]] = None,
                       header_right_fn=None, subheader_fn=None, show_scope_selector=False):
    """Auth required; optionally run page-specific loaders after guard."""
    loader = compose_loaders(
        AuthState.redirect_if_not_authenticated,
        *(extra_on_load or []),
    )
    app.add_page(
        with_shell(
            body_fn,
            title=title,
            active=active,
            header_right_fn=header_right_fn,
            subheader_fn=subheader_fn,
            show_scope_selector=show_scope_selector,
        ),
        route=route,
        on_load=loader,
    )


def add_admin_page(app: rx.App, *, route: str, body_fn, title: str, active: str,
                   extra_on_load: Optional[Iterable[Callable[[], Optional[object]]]] = None,
                   header_right_fn=None, subheader_fn=None, show_scope_selector=False):
    """Org admin required."""
    loader = compose_loaders(
        AuthState.redirect_if_not_admin,
        *(extra_on_load or []),
    )
    app.add_page(
        with_shell(
            body_fn,
            title=title,
            active=active,
            header_right_fn=header_right_fn,
            subheader_fn=subheader_fn,
            show_scope_selector=show_scope_selector,
        ),
        route=route,
        on_load=loader,
    )


def add_super_admin_page(app: rx.App, *, route: str, body_fn, title: str, active: str,
                         extra_on_load: Optional[Iterable[Callable[[], Optional[object]]]] = None,
                         header_right_fn=None, subheader_fn=None, show_scope_selector=False):
    """Super admin required."""
    loader = compose_loaders(
        AuthState.redirect_if_not_super_admin,
        *(extra_on_load or []),
    )
    app.add_page(
        with_shell(
            body_fn,
            title=title,
            active=active,
            header_right_fn=header_right_fn,
            subheader_fn=subheader_fn,
            show_scope_selector=show_scope_selector,
        ),
        route=route,
        on_load=loader,
    )
