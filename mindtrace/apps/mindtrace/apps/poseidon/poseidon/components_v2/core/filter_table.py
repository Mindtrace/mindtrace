import reflex as rx
from typing import Any

def InspectionDetailsModal(state: type[rx.State]) -> rx.Component:
    def _kv(label: str, value: Any):
        return rx.card(
            rx.vstack(
                rx.text(label, size="2", color="gray", weight="medium"),
                rx.text(value, size="4", weight="bold"),
                spacing="1",
            ),
            padding="12px",
            radius="large",
            width="100%",
        )

    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.text("Inspection Details", weight="bold", size="6"),
                rx.grid(
                    _kv("Serial Number", state.selected_serial_number),
                    _kv("Part",          state.selected_part),
                    _kv("Created At",    state.selected_created_at),
                    _kv("Result",        state.selected_result),
                    columns="2",
                    gap="12px",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            close_button=True,
            size="4",
            border_radius="20px",
            max_width="900px",
            width="95vw",
            padding="18px",
        ),
        open=state.modal_open,
        on_open_change=state.set_modal,
    )


# ---------- Filter bar (search + result) ----------
def FilterBar(state: type[rx.State]) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.text("Filters", weight="bold", size="5"),
                rx.spacer(),
                rx.input(
                    placeholder="Search by serial number…",
                    value=state.search,
                    on_change=state.set_search,
                    width="280px",
                    size="3",
                ),
                rx.button("Clear", variant="soft", on_click=state.clear_filters),
                width="100%",
                align="center",
            ),
            rx.hstack(
                rx.vstack(
                    rx.text("Result", size="2", weight="medium"),
                    rx.select(
                        ["All", "Defective", "Healthy"],
                        value=state.result_filter,
                        on_change=state.set_result_filter,
                        size="3",
                        radius="large",
                        width="220px",
                    ),
                    width="220px",
                ),
                width="100%",
                align="center",
                spacing="4",
            ),
            spacing="4",
            width="100%",
        ),
        padding="16px",
        width="100%",
    )


# ---------- Table ----------
CELL_STYLE = dict(padding="8px 12px", font_size="11px")

def DataGrid(state: type[rx.State]) -> rx.Component:
    # --- Cell renderer ---
    def _cell(c, r):
        cid = c["id"]
        val = r.get(cid, "")

        return rx.cond(
            cid == "serial_number",
            rx.box(
                rx.tooltip(
                    content=str(val),
                    child=rx.text(
                        str(val),
                        size="2",
                        no_of_lines=1,
                        max_width="240px",
                        white_space="nowrap",
                        overflow="hidden",
                        text_overflow="ellipsis",
                        display="block",
                    ),
                ),
                **CELL_STYLE,
            ),
            rx.box(
                rx.text(
                    str(val),
                    size="2",
                    no_of_lines=1,
                    max_width="160px",
                    white_space="nowrap",
                    overflow="hidden",
                    text_overflow="ellipsis",
                    display="block",
                ),
                **CELL_STYLE,
            ),
        )

    # --- Accordion row header ---
    def _row_header(r):
        return rx.grid(
            rx.foreach(state.columns_norm, lambda c: _cell(c, r)),
            columns=state.columns_css,   # <- uses our custom widths below
            padding_y="10px",
            border_bottom="1px solid var(--gray-4)",
            align_items="center",
            width="100%",
        )

    # unchanged _row_content / _row etc...
    def _row(r):
        return rx.accordion.item(
            header=_row_header(r),
            content=rx.box(),  # you can keep your parts grid here
            value=f"item_{r['serial_number']}",
            class_name="acc-container",
        )

    return rx.card(
        rx.vstack(
            # header row
            rx.grid(
                rx.foreach(
                    state.columns_norm,
                    lambda c: rx.button(
                        c["header"],
                        variant="ghost",
                        color_scheme="gray",
                        on_click=lambda cid=c["id"]: state.set_sort(cid),
                    ),
                ),
                columns=state.columns_css,
                border_bottom="1px solid var(--gray-6)",
                padding_y="36px",
                width="100%",
            ),
            # rows
            rx.cond(
                state.has_rows,
                rx.accordion.root(
                    rx.foreach(state.rows, _row),
                    type="single",
                    collapsible=True,
                    width="100%",
                    background_color="white",
                ),
                rx.center(rx.text("No results"), padding_y="24px"),
            ),
            # pagination
            rx.hstack(
                rx.text(state.pagination_label, color_scheme="gray"),
                rx.spacer(),
                rx.icon_button("chevron-left", on_click=state.prev_page, disabled=state.prev_disabled),
                rx.icon_button("chevron-right", on_click=state.next_page, disabled=state.next_disabled),
                align="center",
                width="100%",
                padding_top="8px",
            ),
            spacing="3",
            width="100%",
        ),
        padding="0px 16px 12px 16px",
        width="100%",
    )


# ---------- Page wrapper ----------
def FilterTable(state: type[rx.State]) -> rx.Component:
    return rx.vstack(
        FilterBar(state),
        rx.box(height="8px"),
        DataGrid(state),
        InspectionDetailsModal(state),
        width="100%",
        spacing="3",
        on_mount=state.load,
    )
