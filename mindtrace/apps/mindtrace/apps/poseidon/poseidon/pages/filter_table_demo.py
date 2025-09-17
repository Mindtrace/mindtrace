import reflex as rx
from poseidon.pages.lineview.filter_table import FilterTable
from poseidon.state.line_view_state import LineViewState

from poseidon.components_v2.containers.page_container import page_container
from poseidon.components_v2.core.button import button
from poseidon.state.auth import AuthState


def filter_table_demo() -> rx.Component:
    """Authenticated content wrapped in the shared page container."""
    return page_container(
        FilterTable(LineViewState),
        title="Line View",
        sub_text="Inspection traceability and accountability",
    )
