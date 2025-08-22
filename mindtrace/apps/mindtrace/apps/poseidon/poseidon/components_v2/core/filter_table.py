import reflex as rx
from typing import Any
from poseidon.styles.variants import COMPONENT_VARIANTS

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

    def _timeline_item(
        title: str,
        desc_children: list[Any],
        ago: Any,
        color: str,
        badge: str | None = None,
        scheme: str = "gray",
    ):
        return rx.hstack(
            rx.box(width="4px", height="100%", background_color=f"{color}.6", border_radius="2px"),
            rx.vstack(
                rx.hstack(
                    rx.text(title, weight="bold"),
                    rx.spacer(),
                    rx.text(ago, color="gray", size="2"),
                ),
                rx.text(*desc_children, color="gray"),
                rx.badge(badge, variant="soft", color_scheme=scheme) if badge else rx.box(),
                spacing="1",
                width="100%",
            ),
            align="start",
            spacing="3",
            width="100%",
        )

    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                # LEFT: image + legend
                rx.card(
                    rx.box(
                        rx.image(
                            src="https://placehold.co/600x400",
                            alt="Inspection image",
                            width="100%",
                            height="auto",
                            border_radius="16px",
                        ),
                        rx.badge(
                            "AI: ", state.selected_ai_labels,
                            color_scheme="blue",
                            variant="solid",
                            position="absolute", top="16px", left="16px",
                        ),
                        rx.badge(
                            "Human: ", state.selected_operator_label,
                            color_scheme="green",
                            variant="solid",
                            position="absolute", top="56px", left="16px",
                        ),
                        position="relative",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.hstack(
                            rx.box(width="10px", height="10px", border_radius="50%", background_color="blue"),
                            rx.text("AI Detection", size="2"),
                        ),
                        rx.hstack(
                            rx.box(width="10px", height="10px", border_radius="50%", background_color="green"),
                            rx.text("Human Detection", size="2"),
                        ),
                        spacing="4",
                    ),
                    padding="16px",
                    width="60%",
                ),
                # RIGHT: summary + timeline + comments
                rx.vstack(
                    rx.text("Inspection Details - ", state.selected_part_number, weight="bold", size="6"),
                    rx.text(
                        "Detailed view of inspection results, annotations, timeline, and operator comments",
                        color="gray",
                    ),
                    rx.grid(
                        _kv("Station",       state.selected_station),
                        _kv("Operator",      state.selected_operator),
                        _kv("Model Version", state.selected_model_version),
                        _kv("Confidence",    state.selected_confidence),
                        columns="2",
                        gap="12px",
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Event Timeline", weight="bold", size="4"),
                        _timeline_item(
                            "AI Detection",
                            [state.selected_defect_desc, " with ", state.selected_confidence, " confidence"],
                            state.selected_ai_time_ago,
                            "orange",
                            "In Progress",
                            "orange",
                        ),
                        _timeline_item(
                            "Operator Confirmation",
                            [state.selected_operator, " confirmed the detection"],
                            state.selected_op_time_ago,
                            "green",
                            "Success",
                            "green",
                        ),
                        _timeline_item(
                            "Defect Logged",
                            ["Part flagged for rework"],
                            state.selected_log_time_ago,
                            "green",
                        ),
                        spacing="3",
                        padding="8px 0",
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Operator’s Comments", weight="bold", size="4"),
                        rx.card(
                            rx.vstack(
                                rx.text(state.selected_operator, weight="bold"),
                                rx.text(state.selected_comment),
                                rx.text(state.selected_comment_time_ago, size="2", color="gray"),
                                spacing="1",
                            ),
                            padding="12px",
                            width="100%",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    spacing="4",
                    width="40%",
                ),
                align="start",
                spacing="4",
                width="100%",
            ),
            close_button=True,
            size="4",
            border_radius="20px",
            max_width="1100px",
            width="95vw",
            padding="18px",
        ),
        open=state.modal_open,
        on_open_change=state.set_modal,
    )



def FilterBar(state: type[rx.State]) -> rx.Component:
    def _render_filter(f: dict[str, Any]):
        fid = f["id"]
        return rx.vstack(
            rx.text(f["label"], size="2", weight="medium"),
            rx.select(
                state.available_filter_options[fid],
                value=state.filters.get(fid, "All"),
                on_change=lambda v, fid=fid: state.set_filter(fid, v),
                size="3",
                radius="large",
                width="100%",
            ),
            width="100%",
        )

    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.text("Filters", weight="bold", size="5"),
                rx.spacer(),
                rx.input(
                    placeholder="Search...",
                    value=state.search,
                    on_change=state.set_search,
                    width="280px",
                    size="3",
                ),
                rx.button("Clear", variant="soft", on_click=state.clear_filters),
                width="100%",
                align="center",
            ),
            rx.grid(
                rx.foreach(state.filter_config_norm, _render_filter),
                columns="repeat(auto-fit, minmax(200px, 1fr))",
                gap="16px",
                width="100%",
            ),
            spacing="4",
            width="100%",
        ),
        padding="16px",
        width="100%",
    )

# ------ Base style applied to every cell ------
CELL_STYLE = dict(
    padding="8px 12px",
    font_size="11px",
)

# ------ Badge color maps ------
DEFECT_BADGE = {
    "Surface": "red",
    "Weld": "red",
    "Missing": "red",
    "Alignment": "amber",
    "None": "gray",
}
OPERATOR_BADGE = {
    "Normal Wear": "amber",
    "Weld Defect": "orange",
    "Pass": "amber",
    "-": "gray",
}
OUTCOME_BADGE = {
    "Pass": "green",
    "Confirmed": "red",
    "Override": "amber",
    "Catch": "blue",
}

# ------ Helpers ------
def _soft_badge(text: str, scheme: str):
    return rx.badge(text, color_scheme=scheme, variant="soft")

def color_from_map(val, mapping: dict[str, str], default: str = "gray"):
    """Build a color *expression* with rx.cond so it works with Vars."""
    expr = default
    for k, v in mapping.items():
        expr = rx.cond(val == k, v, expr)
    return expr

def DataGrid(state: type[rx.State]) -> rx.Component:
    # --- Cell renderer (unchanged) ---
    def _cell(c, r):
        cid = c["id"]
        val = r[cid]

        return rx.box(
            rx.cond(
                cid == "defect_type",
                _soft_badge(val, color_from_map(val, DEFECT_BADGE)),
                rx.cond(
                    cid == "operator",
                    _soft_badge(val, color_from_map(val, OPERATOR_BADGE)),
                    rx.cond(
                        cid == "outcome",
                        _soft_badge(val, color_from_map(val, OUTCOME_BADGE)),
                        rx.cond(
                            cid == "confidence",
                            rx.text(val, font_weight="semibold"),
                            rx.cond(
                                cid == "image",
                                rx.button(
                                    "View",
                                    variant="soft",
                                    on_click=lambda rr=r: state.open_inspection(rr),
                                    size="2",
                                ),
                                rx.text(val),
                            ),
                        ),
                    ),
                ),
            ),
            **CELL_STYLE,
        )

    # --- Accordion row header: your original grid for a row ---
    def _row_header(r):
        return rx.grid(
            rx.foreach(state.columns_norm, lambda c: _cell(c, r)),
            columns=state.columns_css,
            padding_y="10px",
            border_bottom="1px solid var(--gray-4)",
            align_items="center",
            width="100%",
        )

    # --- Accordion row content: dropdown + a free area to build components ---
    def _row_content(r):
        return rx.flex(
            rx.dropdown_menu.root(
                rx.dropdown_menu.trigger(
                    rx.button("Row actions", size="2", variant="soft")
                ),
                rx.dropdown_menu.content(
                    rx.dropdown_menu.item(
                        "Open inspection",
                        on_select=lambda rr=r: state.open_inspection(rr),
                    ),
                    rx.dropdown_menu.item("Edit (stub)"),
                    rx.dropdown_menu.item("Duplicate (stub)"),
                    rx.dropdown_menu.separator(),
                    rx.dropdown_menu.item("Archive (stub)"),
                ),
            ),
            rx.box(
                rx.text(
                    "Add an operator note or change the status of this inspection.",
                    weight="medium",
                ),
                rx.hstack(
                    rx.input(
                        placeholder="Add a note…",
                        width="300px",
                    ),
                    rx.switch(label="Enabled"),
                    rx.button("Save", variant="soft", size="2"),
                    spacing="3",
                    wrap="wrap",
                ),
                padding="12px",
                width="100%",
                border_top="1px solid var(--gray-3)",
                background_color="var(--gray-2)",
                border_radius="10px",
            ),
            direction="column",
            gap="10px",
            width="100%",
            padding_top="8px",
        )


    # --- One accordion item per row ---
    def _row(r):
        return rx.accordion.item(
            header=_row_header(r),
            content=_row_content(r),
            value=f"row_{r.get('id', '')}",
            class_name="acc-container",
        )

    # --- Component ---
    return rx.card(
        rx.vstack(
            # Header (sortable)
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
            # Body: rows inside a single accordion
            rx.cond(
                state.has_rows,
                rx.accordion.root(
                    rx.foreach(state.visible_rows_list, _row),
                    type="multiple",      # allow several open at once
                    collapsible=True,
                    width="100%",
                    style=COMPONENT_VARIANTS["table_accordian"],
                    class_name="acc-container"
                ),
                rx.center(rx.text("No results"), padding_y="24px"),
            ),
            # Footer (pagination)
            rx.hstack(
                rx.text(state.pagination_label, color_scheme="gray"),
                rx.spacer(),
                rx.icon_button(
                    "chevron-left",
                    on_click=state.prev_page,
                    disabled=state.prev_disabled,
                ),
                rx.icon_button(
                    "chevron-right",
                    on_click=state.next_page,
                    disabled=state.next_disabled,
                ),
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


def FilterTable(state: type[rx.State]) -> rx.Component:
    return rx.vstack(
        FilterBar(state),
        rx.box(height="8px"),
        DataGrid(state),
        InspectionDetailsModal(state),
        width="100%",
        spacing="3",
    )
