import reflex as rx
from mindtrace.ui.playground.storybook import storybook_page


def index() -> rx.Component:
    """Simple landing page with a link to the storybook."""
    return rx.center(
        rx.vstack(
            rx.heading("Mindtrace UI"),
            rx.text("Component library & playground"),
            rx.link("Open Storybook", href="/storybook"),
            spacing="4",
            align="center",
        ),
        min_height="100vh",
        padding="2rem",
    )


# ---- App ----
app = rx.App()
app.add_page(index, route="/", title="Mindtrace UI")
app.add_page(storybook_page, route="/storybook", title="Mindtrace UI — Storybook")
