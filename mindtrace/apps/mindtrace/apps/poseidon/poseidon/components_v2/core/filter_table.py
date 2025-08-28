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
                    _kv("Operator",      state.selected_operator),
                    _kv("Model Version", state.selected_model_version),
                    _kv("Confidence",    state.selected_confidence),
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

        def _truncated_text(v, max_px: int):
            return rx.text(
                v,
                size="2",
                no_of_lines=1,
                max_width=f"{max_px}px",
                title=v,
                color="black",
            )

        serial_cell = rx.box(
            rx.link(
                _truncated_text(val, 240),
                href="#",
                on_click=lambda rr=r: state.open_inspection(rr),
            ),
            **CELL_STYLE,
        )

        default_cell = rx.box(
            _truncated_text(val, 160),
            **CELL_STYLE,
        )

        return rx.cond(
            cid == "serial_number",
            serial_cell,
            default_cell,
        )


    # --- Accordion row header ---
    def _row_header(r):
        return rx.grid(
            rx.foreach(state.columns_norm, lambda c: _cell(c, r)),
            columns=state.columns_css,
            padding_y="10px",
            border_bottom="1px solid var(--gray-4)",
            align_items="center",
            width="100%",
            color="black",
        )

    def _row_content(r):
        serial = r.get("serial_number", "Unknown")
        
        def _camera_chip(camera):
            """Individual camera status chip using STATE data."""
            return rx.box(
                # Camera name header
                rx.box(
                    rx.text(camera["name"], weight="bold", size="2"),
                    background_color="white",
                    border="1px solid var(--gray-4)",
                    border_bottom="0",
                    padding="6px 8px",
                    border_top_left_radius="10px",
                    border_top_right_radius="10px",
                    text_align="center",
                ),
                # Status colored section
                rx.box(
                    rx.center(
                        rx.text(
                            camera["status"], 
                            weight="medium", 
                            size="3",
                            color=rx.cond(camera["status"] == "Healthy", "black", "white")
                        ),
                        width="100%", 
                        height="52px",
                    ),
                    background_color=rx.cond(camera["status"] == "Healthy", "#86efac", "#fca5a5"),
                    border="1px solid var(--gray-4)",
                    border_top="0",
                    border_bottom_left_radius="10px",
                    border_bottom_right_radius="10px",
                ),
                cursor="pointer",
                _hover={"box_shadow": "0 0 0 2px var(--gray-6) inset"},
                min_width="120px",
            )
        
        return rx.box(
            rx.text("Camera Status:", weight="bold", size="3", margin_bottom="8px"),
            rx.text(f"Serial: {serial}", size="2", color="gray", margin_bottom="8px"),
            rx.cond(
                state.expanded_row_serial == serial,
                rx.grid(
                    # THE KEY: Use state variable directly, like all other components!
                    rx.foreach(state.current_row_cameras, _camera_chip),
                    columns="repeat(auto-fit, minmax(120px, 1fr))",
                    gap="12px",
                    width="100%",
                ),
                rx.text("Click to expand and see camera data", size="2", color="gray")
            ),
            padding="12px",
            width="100%",
        )
        # def _status_chip(item):
        #     name, status = item
        #     bg = rx.cond(status == "Healthy", "#86efac", "#fca5a5")
        #     fg = rx.cond(status == "Healthy", "black", "white")

        #     return rx.box(
        #         rx.box(
        #             rx.text(name, weight="bold", size="2"),
        #             background_color="white",
        #             border="1px solid var(--gray-4)",
        #             border_bottom="0",
        #             padding="6px 8px",
        #             border_top_left_radius="10px",
        #             border_top_right_radius="10px",
        #         ),
        #         rx.box(
        #             rx.center(
        #                 rx.text(status, weight="medium", size="3", color=fg),
        #                 width="100%", height="52px",
        #             ),
        #             background_color=bg,
        #             border="1px solid var(--gray-4)",
        #             border_top="0",
        #             border_bottom_left_radius="10px",
        #             border_bottom_right_radius="10px",
        #         ),
        #         on_click=lambda rr=r: state.open_inspection(rr),
        #         cursor="pointer",
        #         _hover={"box_shadow": "0 0 0 2px var(--gray-6) inset"},
        #     )

        # return rx.box(
        #     rx.grid(
        #         rx.foreach(list(parts.items()), _status_chip),  # <-- FIXED
        #         columns="repeat(10, 1fr)",
        #         gap="12px",
        #         width="100%",
        #     ),
        #     padding="12px 0",
        #     width="100%",
        # )

    def _row(r):
        return rx.accordion.item(
            header=_row_header(r),
            content=_row_content(r),
            value=f"item_{r['serial_number']}",
            class_name="hover:[&>h3>button]:bg-white [&>h3>button]:text-black",
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
                    background_color="white !important",
                    class_name="acc-container",
                    on_value_change=state.handle_accordion_change,
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
