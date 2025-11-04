import reflex as rx

from inspectra.components.app_shell import AppShell
from inspectra.pages.index import index
from inspectra.pages.login import login
from inspectra.styles.global_styles import global_css

app = rx.App(
    theme=rx.theme(
        appearance="light",
        accent_color="blue",
        radius="medium",
        font_family="Inter",
    ),
)


def wrap_in_shell(page_fn):
    def _page_wrapper(*args, **kwargs):
        return AppShell(page_fn(*args, **kwargs))

    return _page_wrapper


# Inject global CSS
app.head_components.append(global_css())

# Routes
app.add_page(wrap_in_shell(index), route="/")
app.add_page(wrap_in_shell(index), route="/alerts")
app.add_page(wrap_in_shell(index), route="/reports")

# Login — no AppShell
app.add_page(login, route="/login")
