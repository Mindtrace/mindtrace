import reflex as rx
from poseidon.components_v2.core.filter_table import FilterTable
from poseidon.state.grid_state import GridState


def filter_table_demo() -> rx.Component:
    return rx.container(
        rx.heading("Audit Trail", size="6", weight="bold"),
        rx.text("Inspection traceability and accountability", color_scheme="gray"),
        rx.box(height="8px"),
        FilterTable(GridState),
        padding_y="24px",
        width="100%",
        size="4",
    )