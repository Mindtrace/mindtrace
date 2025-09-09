import reflex as rx
from typing import Any, Dict, List

# =========================
# Column schema
# =========================
COLUMNS_SCHEMA: List[Dict[str, str]] = [
    {"title": "Serial Number", "key": "serial_number", "type": "str"},
    {"title": "Part",          "key": "part",           "type": "str"},
    {"title": "Created At",    "key": "created_at",     "type": "str"},
    {"title": "Result",        "key": "result",         "type": "str"},
]

COL_WIDTHS: Dict[str, str] = {
    "serial_number": "280px",
    "part":          "160px",
    "created_at":    "220px",
    "result":        "120px",
    "_chevron":      "40px",
}

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
        label_text = rx.cond(
            state.selected_part_status != "",
            state.selected_part_status,
            rx.cond(state.selected_result != "", state.selected_result, "—"),
        )

        bg_color = rx.cond(label_text == "Healthy", "#86efac", "#ef4444")
        fg_color = rx.cond(label_text == "Healthy", "black", "white")
        border_color = bg_color

        bbox_overlay = rx.cond(
            state.show_bbox,
            rx.box(
                rx.box(
                    rx.text(label_text, weight="bold", size="2"),
                    position="absolute",
                    top="-22px",
                    left="0",
                    padding="2px 8px",
                    background=bg_color,
                    color=fg_color,
                    border_radius="6px",
                    line_height="18px",
                    box_shadow="0 1px 2px rgba(0,0,0,0.25)",
                    white_space="nowrap",
                ),
                position="absolute",
                top="22%",
                left="15%",
                width="50%",
                height="34%",
                border=f"3px solid {border_color}",
                border_radius="4px",
                box_shadow="0 0 0 1px rgba(0,0,0,0.15) inset",
                pointer_events="none",
            ),
            rx.fragment(),
        )

        return rx.box(
            rx.box(
                rx.image(
                    src=state.selected_image_url,
                    alt="inspection image",
                    width="100%",
                    height="65vh",
                    object_fit="contain",
                    border_radius="12px",
                    background="black",
                ),
                bbox_overlay,
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
            rx.text(rx.cond(state.selected_part != "", state.selected_part, "-"), weight="bold", size="5"),
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
            rx.checkbox("Show Bounding Box", checked=state.show_bbox, on_change=state.set_show_bbox),
            rx.box(height="8px"),
            rx.grid(
                _kv("Serial Number", state.selected_serial_number),
                columns="1",
                gap="12px",
                width="100%",
            ),
            spacing="4",
            width="420px",
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
# Expandable Table (summary + details rows)
# =========================

def _text_cell(value, key: str) -> rx.Component:
    safe_value = rx.cond(value != "", value, "-")
    pad_x = "8px" if key == "serial_number" else "12px"
    return rx.table.cell(
        rx.text(
            safe_value,
            size="2",
            weight="regular",
            style={
                "display": "block",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
                "whiteSpace": "nowrap",
            },
        ),
        width=COL_WIDTHS.get(key, "auto"),
        padding=f"10px {pad_x}",
        text_align="left",
    )

def _serial_cell(serial) -> rx.Component:
    safe_label = rx.cond(serial != "", serial, "-")
    return rx.table.cell(
        rx.tooltip(
            rx.text(
                safe_label,
                underline="always",
                style={
                    "display": "block",
                    "overflow": "hidden",
                    "textOverflow": "ellipsis",
                    "whiteSpace": "nowrap",
                },
            ),
            content=safe_label,
            side="top",
        ),
        width=COL_WIDTHS["serial_number"],
        padding="10px 8px",
        text_align="left",
    )

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
                max_width="140px",
            ),
            href="#",
            on_click=lambda cam=camera, rr=row: state.open_part_preview(rr, cam),
        ),
        width="100%",
    )

def _expand_cell(state: type[rx.State], row_id: str) -> rx.Component:
    return rx.table.cell(
        rx.icon_button(
            "chevron-down",
            size="2",
            variant="ghost",
            on_click=lambda rid=row_id: state.toggle_row(rid),
            style={
                "transition": "transform 150ms ease",
                "transform": rx.cond(
                    state.expanded_row_id == row_id, "rotate(180deg)", "rotate(0deg)"
                ),
                "margin-top": "3px",
                "color": "black",
                "cursor": "pointer",
            },
        ),
        width=COL_WIDTHS["_chevron"],
        padding="0 4px",
        text_align="center",
        cursor="pointer",
    )

def _summary_row(state: type[rx.State], r: Dict[str, Any]) -> rx.Component:
    cells: List[rx.Component] = []
    for col in COLUMNS_SCHEMA:
        key = col["key"]
        if key == "serial_number":
            cells.append(_serial_cell(r.get("serial_number", "")))
        else:
            cells.append(_text_cell(r.get(key, ""), key))
    cells.append(_expand_cell(state, r["id"]))

    return rx.table.row(
        *cells,
        class_name="hover:bg-[var(--gray-2)]",
    )

def _details_row(state: type[rx.State], r: Dict[str, Any]) -> rx.Component:
    """Always render a details <tr>, toggle visibility with CSS."""
    return rx.table.row(
        rx.table.cell(
            rx.box(
                rx.cond(
                    state.parts_loading & (state.expanded_row_id == r["id"]),
                    rx.center(rx.spinner(size="3"), padding="12px"),
                    rx.grid(
                        rx.foreach(
                            state.current_row_cameras,
                            lambda cam: _camera_chip(cam, state, r),
                        ),
                        columns="repeat(auto-fit, minmax(140px, 1fr))",
                        gap="12px",
                        width="100%",
                    ),
                ),
                padding="12px",
                width="100%",
            ),
            col_span=len(COLUMNS_SCHEMA) + 1,
            style={"background": "white", "borderTop": "1px solid var(--gray-4)"},
        ),
        style={
            "display": rx.cond(
                state.expanded_row_id == r["id"], "table-row", "none"
            )
        },
        class_name="border-b border-[var(--gray-4)]",
    )

def _table_header(state: type[rx.State]) -> rx.Component:
    header_cells: List[rx.Component] = []
    for col in COLUMNS_SCHEMA:
        key = col["key"]
        title = col["title"]
        width = COL_WIDTHS.get(key, "auto")
        if key == "created_at":
            cell = rx.table.column_header_cell(
                rx.hstack(
                    rx.text(title, weight="medium"),
                    rx.cond(
                        state.sort_by == "created_at",
                        rx.text(
                            rx.cond(state.sort_dir == "asc", "▲", "▼"), size="1"
                        ),
                        rx.box(),
                    ),
                    spacing="2",
                    align="center",
                ),
                on_click=lambda: state.set_sort("created_at"),
                cursor="pointer",
                padding_y="14px",
                width=width,
                text_align="left",
            )
        else:
            cell = rx.table.column_header_cell(
                title,
                width=width,
                text_align="left",
            )
        header_cells.append(cell)
    header_cells.append(
        rx.table.column_header_cell("", width=COL_WIDTHS["_chevron"], text_align="center")
    )

    return rx.table.header(
        rx.table.row(*header_cells, class_name="border-b border-[var(--gray-4)]"),
    )

def DataGrid(state: type[rx.State]) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.table.root(
                _table_header(state),
                rx.table.body(
                    rx.foreach(
                        state.rows,
                        lambda r: rx.fragment(
                            _summary_row(state, r),
                            _details_row(state, r),
                        ),
                    )
                ),
                width="100%",
                style={"tableLayout": "fixed"},
                class_name="bg-white",
            ),
            rx.hstack(
                rx.text(state.pagination_label, color_scheme="gray"),
                rx.spacer(),
                rx.icon_button(
                    "chevron-left", on_click=state.prev_page, disabled=state.prev_disabled
                ),
                rx.icon_button(
                    "chevron-right", on_click=state.next_page, disabled=state.next_disabled
                ),
                align="center",
                width="100%",
                padding_top="8px",
            ),
            spacing="8",
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
