import reflex as rx
from poseidon.components_v2.core.filter_table import FilterTable
from poseidon.state.grid_state import GridState

from poseidon.components_v2.containers.page_container import page_container
from poseidon.components_v2.core.button import button
from poseidon.state.auth import AuthState


def _login_gate() -> rx.Component:
    """Shown when the user is not authenticated."""
    return rx.center(
        rx.vstack(
            rx.text("🔒", font_size="4rem", color="#9CA3AF"),
            rx.text("Access Denied", font_size="2rem", font_weight="600", color="#374151"),
            rx.text("Please log in to view the Line View", color="#6B7280", text_align="center"),
            rx.link(rx.button("Go to Login", color_scheme="blue", size="3"), href="/login"),
            spacing="4",
            align="center",
        ),
        height="100vh",
        width="100%",
    )


def _content() -> rx.Component:
    """Authenticated content wrapped in the shared page container."""
    return page_container(
        FilterTable(GridState),
        title="Line View",
        sub_text="Inspection traceability and accountability",
        tools=[
            button(
                "Refresh",
                icon=rx.icon("refresh-cw"),
                on_click=GridState.load,
                variant="secondary",
            ),
        ],
    )


def filter_table_demo() -> rx.Component:
    """Route component for /filter-table-demo."""
    return rx.cond(
        AuthState.is_authenticated,
        rx.box(
            _content(),
            width="100%",
            min_height="100vh",
        ),
        _login_gate(),
    )
