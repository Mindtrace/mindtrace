import reflex as rx
from typing import Any, Dict


# =========================
# Modal
# =========================
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

    def _image_panel() -> rx.Component:
        return rx.box(
            rx.box(
                rx.image(
                    src=rx.cond(
                        state.selected_image_url != "",
                        state.selected_image_url,
                        "/placeholder.png",
                    ),
                    alt="inspection image",
                    width="100%",
                    height="65vh",
                    object_fit="contain",
                    border_radius="12px",
                    background="black",
                ),
                position="relative",
                width="100%",
                height="65vh",
                overflow="hidden",
                border_radius="12px",
            ),
            width="100%",
        )

    def _details_panel() -> rx.Component:
        return rx.vstack(
            rx.text(
                rx.cond(state.selected_part != "", state.selected_part, "-"),
                weight="bold",
                size="5",
            ),
            rx.box(height="4px"),
            rx.card(
                rx.vstack(
                    rx.text("Detected class", weight="medium", size="2", color="gray"),
                    rx.text(
                        rx.cond(
                            state.selected_part_status != "",
                            state.selected_part_status,
                            rx.cond(state.selected_result != "", state.selected_result, "-"),
                        ),
                        weight="bold",
                        size="4",
                    ),
                    spacing="2",
                ),
                padding="12px",
                radius="large",
                width="100%",
            ),
            rx.checkbox(
                "Show Bounding Box",
                checked=state.show_bbox,
                on_change=state.set_show_bbox,
            ),
            rx.box(height="8px"),
            rx.card(
                rx.vstack(
                    rx.text("Detected labels", weight="medium", size="2", color="gray"),
                    rx.vstack(
                        rx.foreach(
                            state.selected_part_classes,
                            lambda cls: rx.text(f"- {cls}", size="3"),
                        ),
                        spacing="1",
                        align="start",
                        width="100%",
                    ),
                    spacing="2",
                ),
                padding="12px",
                radius="large",
                width="100%",
            ),
            rx.grid(
                _kv("Serial Number", state.selected_serial_number),
                _kv("Created At",    state.selected_created_at),
                _kv(
                    "Operator",
                    rx.cond(state.selected_operator != "", state.selected_operator, "-"),
                ),
                _kv(
                    "Model Version",
                    rx.cond(state.selected_model_version != "", state.selected_model_version, "-"),
                ),
                _kv(
                    "Confidence",
                    rx.cond(
                        state.selected_part_confidence != "",
                        state.selected_part_confidence,
                        rx.cond(state.selected_confidence != "", state.selected_confidence, "-"),
                    ),
                ),
                columns="1",
                gap="12px",
                width="100%",
            ),
            spacing="4",
            width="360px",
        )

    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.text("Inspection Details", weight="bold", size="6"),
                rx.grid(
                    _image_panel(),
                    _details_panel(),
                    columns="2",
                    gap="16px",
                    width="100%",
                    align_items="start",
                ),
                spacing="4",
                width="100%",
            ),
            close_button=True,
            size="4",
            border_radius="20px",
            max_width="1200px",
            width="95vw",
            padding="18px",
        ),
        open=state.modal_open,
        on_open_change=state.set_modal,
    )


# =========================
# Filter bar
# =========================
def FilterBar(state: type[rx.State]) -> rx.Component:
    return rx.card(
        rx.vstack(
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
            spacing="4",
            width="100%",
        ),
        padding="16px",
        width="100%",
    )


# =========================
# Accordion + Table header
# =========================

CELL_STYLE = dict(width="264px",padding="10px 12px", font_size="12px", text_align="left", overflow="hidden", text_overflow="ellipsis", white_space="nowrap")
COLUMNS_CSS = "1fr 1fr 1fr 1fr auto"


def _camera_chip(camera: Dict[str, Any], state: type[rx.State], row: Dict[str, Any]):
    return rx.box(
        rx.link(
            rx.box(
                rx.box(
                    rx.text(camera.get("name", "-"), weight="bold", size="2"),
                    background_color="white",
                    border="1px solid var(--gray-4)",
                    border_bottom="0",
                    padding="6px 8px",
                    border_top_left_radius="10px",
                    border_top_right_radius="10px",
                    text_align="center",
                    color="black",
                ),
                rx.box(
                    rx.center(
                        rx.text(
                            camera.get("status", "-"),
                            weight="medium",
                            size="3",
                            color=rx.cond(
                                camera.get("status", "") == "Healthy", "black", "white"
                            ),
                        ),
                        width="100%",
                        height="52px",
                    ),
                    background_color=rx.cond(
                        camera.get("status", "") == "Healthy", "#86efac", "#fca5a5"
                    ),
                    border="1px solid var(--gray-4)",
                    border_top="0",
                    border_bottom_left_radius="10px",
                    border_bottom_right_radius="10px",
                ),
                cursor="pointer",
                _hover={"box_shadow": "0 0 0 2px var(--gray-6) inset"},
                max_width="120px",
            ),
            href="#",
            on_click=lambda cam=camera, rr=row: state.open_part_preview(rr, cam),
        ),
        **CELL_STYLE,
    )


def _row_header_grid(state: type[rx.State], r: Dict[str, Any]) -> rx.Component:
    """Grid that *looks* like a table row (inside accordion header)."""
    return rx.grid(
        rx.box(
            rx.text(r.get("serial_number", "-"), underline="always"),
            **CELL_STYLE,
        ),
        rx.box(rx.text(r.get("part", "-")), **CELL_STYLE),
        rx.box(rx.text(r.get("created_at", "-")), **CELL_STYLE),
        rx.box(rx.text(r.get("result", "-")), **CELL_STYLE),
        rx.box(
            rx.icon("chevron-down", size=16),
            display="flex",
            align_items="center",
            justify_content="center",
            padding_right="8px",
            color="var(--gray-9)",
        ),
        columns=COLUMNS_CSS,
        align_items="center",
        width="100%",
        border_bottom="1px solid var(--gray-4)",
    )


def _accordion_row(state: type[rx.State], r: Dict[str, Any]) -> rx.Component:
    return rx.accordion.item(
        header=_row_header_grid(state, r),
        content=rx.box(
            rx.grid(
                rx.foreach(
                    state.current_row_cameras,
                    lambda cam: _camera_chip(cam, state, r),
                ),
                columns="repeat(auto-fit, minmax(120px, 1fr))",
                gap="12px",
                width="100%",
            ),
            padding="12px",
            width="100%",
        ),
        value=f"item_{r['id']}",
        class_name=(
            "hover:[&>h3>button]:bg-white [&>h3>button]:text-black "
            "[&>h3>button]:p-0 [&>h3>button]:m-0"
        ),
    )

def DataGrid(state: type[rx.State]) -> rx.Component:
    return rx.card(
        rx.vstack(
            # ---------------------------
            # Table header (only one sortable column: "Created At")
            # ---------------------------
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Serial Number", width="264px"),
                        rx.table.column_header_cell("Part", width="264px"),
                        rx.table.column_header_cell(
                            rx.hstack(
                                rx.text("Created At", weight="medium"),
                                rx.cond(
                                    state.sort_by == "created_at",
                                    rx.text(
                                        rx.cond(state.sort_dir == "asc", "▲", "▼"),
                                        size="1",
                                    ),
                                    rx.box(),
                                ),
                                spacing="2",
                                align="center",
                            ),
                            on_click=lambda: state.set_sort("created_at"),
                            cursor="pointer",
                            padding_y="14px",
                            width="264px",
                        ),
                        rx.table.column_header_cell("Result", width="264px"),
                        rx.table.column_header_cell(""),
                        display="flex",
                        gap="15px"
                    )
                ),
                width="100%",
            ),
            # Accordion rows below
            rx.cond(
                state.has_rows,
                rx.accordion.root(
                    rx.foreach(state.rows, lambda r: _accordion_row(state, r)),
                    type="single",
                    collapsible=True,
                    width="100%",
                    background_color="white !important",
                    class_name="acc-container",
                    on_value_change=state.handle_accordion_change,
                ),
                rx.center(rx.text("No results"), padding_y="24px"),
            ),
            # Pagination
            rx.hstack(
                rx.text(state.pagination_label, color_scheme="gray"),
                rx.spacer(),
                rx.icon_button("chevron-left", on_click=state.prev_page, disabled=state.prev_disabled),
                rx.icon_button("chevron-right", on_click=state.next_page, disabled=state.next_disabled),
                align="center",
                width="100%",
                padding_top="8px",
            ),
            spacing="0",
            width="100%",
        ),
        padding="0px 16px 12px 16px",
        width="100%",
    )


# =========================
# Page wrapper
# =========================
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