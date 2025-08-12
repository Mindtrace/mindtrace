"""
Inference page component.

Provides inference interface with:
- Serial number input and model deployment selection
- Scan button with loading state
- Previous scans history table
- Real-time scan results display
"""

import reflex as rx
from poseidon.components import (
    sidebar,
    app_header,
    page_container,
    input_with_label_mindtrace,
    select_mindtrace,
    success_message,
    error_message,
    page_header_with_actions,
    card_mindtrace,
    header_mindtrace,
)
from poseidon.components_v2.core.button import button
from poseidon.state.inference import InferenceState


def inference_form() -> rx.Component:
    """Main inference form with serial number input and deployment selection"""
    return card_mindtrace(
        [
            header_mindtrace(
                "Run Inference Scan", "Enter part serial number and select model deployment to perform inference"
            ),
            rx.vstack(
                # Serial number input
                rx.vstack(
                    rx.el.label(
                        "Part Serial Number",
                        style={
                            "font_size": "0.875rem",
                            "font_weight": "500",
                            "color": "rgb(71, 85, 105)",
                            "margin_bottom": "0.5rem",
                            "display": "block",
                            "font_family": '"Inter", system-ui, sans-serif',
                        },
                    ),
                    rx.el.input(
                        placeholder="Enter serial number...",
                        name="serial_number",
                        type="text",
                        required=True,
                        value=InferenceState.serial_number,
                        on_change=InferenceState.set_serial_number,
                        style={
                            "width": "100%",
                            "padding": "0.75rem 1rem",
                            "font_size": "0.925rem",
                            "font_family": '"Inter", system-ui, sans-serif',
                            "border_radius": "12px",
                            "background": "rgba(248, 250, 252, 0.8)",
                            "border": "2px solid rgba(226, 232, 240, 0.6)",
                            "outline": "none",
                            "transition": "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                            "backdrop_filter": "blur(10px)",
                            "color": "rgb(51, 65, 85)",
                            "_focus": {
                                "border_color": "#0057FF",
                                "background": "rgba(255, 255, 255, 0.95)",
                                "box_shadow": "0 0 0 4px rgba(0, 87, 255, 0.1), 0 4px 12px rgba(0, 87, 255, 0.15)",
                                "transform": "translateY(-1px)",
                            },
                            "_hover": {
                                "border_color": "rgba(0, 87, 255, 0.3)",
                                "background": "rgba(255, 255, 255, 0.9)",
                            },
                            "_placeholder": {
                                "color": "rgba(100, 116, 139, 0.6)",
                            },
                        },
                    ),
                    width="100%",
                    spacing="1",
                    style={
                        "margin_bottom": "0.5rem",
                    },
                ),
                # Model deployment selection
                rx.vstack(
                    rx.el.label(
                        "Model Deployment",
                        style={
                            "font_size": "0.875rem",
                            "font_weight": "500",
                            "color": "rgb(71, 85, 105)",
                            "margin_bottom": "0.5rem",
                            "display": "block",
                            "font_family": '"Inter", system-ui, sans-serif',
                        },
                    ),
                    rx.cond(
                        InferenceState.loading,
                        rx.el.select(
                            rx.el.option("Loading deployments...", value="", disabled=True, selected=True),
                            disabled=True,
                            style={
                                "width": "100%",
                                "padding": "0.75rem 1rem",
                                "font_size": "0.925rem",
                                "font_family": '"Inter", system-ui, sans-serif',
                                "border_radius": "12px",
                                "background": "rgba(243, 244, 246, 0.8)",
                                "border": "2px solid rgba(226, 232, 240, 0.6)",
                                "outline": "none",
                                "color": "rgb(107, 114, 128)",
                                "cursor": "not-allowed",
                            },
                        ),
                        rx.el.select(
                            rx.el.option("Select a deployment...", value="", disabled=True, selected=True),
                            rx.foreach(
                                InferenceState.deployment_options,
                                lambda dep: rx.el.option(dep["name"], value=dep["id"]),
                            ),
                            on_change=InferenceState.set_selected_deployment_id,
                            value=InferenceState.selected_deployment_id,
                            style={
                                "width": "100%",
                                "padding": "0.75rem 1rem",
                                "font_size": "0.925rem",
                                "font_family": '"Inter", system-ui, sans-serif',
                                "border_radius": "12px",
                                "background": "rgba(248, 250, 252, 0.8)",
                                "border": "2px solid rgba(226, 232, 240, 0.6)",
                                "outline": "none",
                                "transition": "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                                "backdrop_filter": "blur(10px)",
                                "color": "rgb(51, 65, 85)",
                                "cursor": "pointer",
                                "_focus": {
                                    "border_color": "#0057FF",
                                    "background": "rgba(255, 255, 255, 0.95)",
                                    "box_shadow": "0 0 0 4px rgba(0, 87, 255, 0.1)",
                                },
                                "_hover": {
                                    "border_color": "rgba(0, 87, 255, 0.3)",
                                    "background": "rgba(255, 255, 255, 0.9)",
                                },
                            },
                        ),
                    ),
                    width="100%",
                    spacing="1",
                    style={
                        "margin_bottom": "0.5rem",
                    },
                ),
                # Scan button
                rx.box(
                    rx.cond(
                        InferenceState.is_scanning,
                        rx.el.button(
                            "Scanning...",
                            disabled=True,
                            style={
                                "width": "100%",
                                "padding": "1rem 2rem",
                                "font_size": "1rem",
                                "font_weight": "600",
                                "font_family": '"Inter", system-ui, sans-serif',
                                "border_radius": "12px",
                                "background": "rgba(107, 114, 128, 0.8)",
                                "color": "white",
                                "border": "none",
                                "cursor": "not-allowed",
                                "transition": "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                            },
                        ),
                        rx.el.button(
                            "Scan",
                            disabled=~InferenceState.can_scan,
                            on_click=InferenceState.run_inference,
                            style={
                                "width": "100%",
                                "padding": "1rem 2rem",
                                "font_size": "1rem",
                                "font_weight": "600",
                                "font_family": '"Inter", system-ui, sans-serif',
                                "border_radius": "12px",
                                "background": rx.cond(
                                    InferenceState.can_scan,
                                    "linear-gradient(135deg, #0057FF 0%, #0041CC 100%)",
                                    "rgba(226, 232, 240, 0.8)",
                                ),
                                "color": rx.cond(InferenceState.can_scan, "white", "rgb(107, 114, 128)"),
                                "border": "none",
                                "cursor": rx.cond(InferenceState.can_scan, "pointer", "not-allowed"),
                                "transition": "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                                "box_shadow": rx.cond(
                                    InferenceState.can_scan, "0 4px 16px rgba(0, 87, 255, 0.3)", "none"
                                ),
                                "_hover": rx.cond(
                                    InferenceState.can_scan,
                                    {
                                        "transform": "translateY(-2px)",
                                        "box_shadow": "0 8px 24px rgba(0, 87, 255, 0.4)",
                                        "background": "linear-gradient(135deg, #0041CC 0%, #003399 100%)",
                                    },
                                    {},
                                ),
                            },
                        ),
                    ),
                    width="100%",
                    margin_top="1rem",
                ),
                width="100%",
                spacing="4",
            ),
        ]
    )


def scan_history_table() -> rx.Component:
    """Table showing previous scans performed since page was opened"""
    return card_mindtrace(
        [
            header_mindtrace("Scan History", "Previous scans performed during this session"),
            rx.cond(
                InferenceState.scan_history.length() > 0,
                rx.box(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Serial Number"),
                                rx.table.column_header_cell("Timestamp"),
                                rx.table.column_header_cell("Result"),
                                rx.table.column_header_cell("Status"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(
                                InferenceState.scan_history,
                                lambda scan: rx.table.row(
                                    rx.table.cell(scan.serial_number),
                                    rx.table.cell(rx.text(scan.formatted_timestamp, font_size="0.875rem")),
                                    rx.table.cell(scan.status),
                                    rx.table.cell(
                                        rx.cond(
                                            scan.is_healthy,
                                            rx.badge("Healthy", color_scheme="green", variant="soft"),
                                            rx.badge("Defective", color_scheme="red", variant="soft"),
                                        )
                                    ),
                                ),
                            )
                        ),
                        size="2",
                        variant="surface",
                        width="100%",
                    ),
                    overflow_x="auto",
                ),
                rx.box(
                    rx.text(
                        "No scans performed yet",
                        color="rgba(107, 114, 128, 0.8)",
                        font_size="0.875rem",
                        text_align="center",
                        padding="2rem",
                    ),
                    width="100%",
                ),
            ),
        ]
    )


def inference_content() -> rx.Component:
    """Main inference page content"""
    return rx.box(
        # Main content
        page_container(
            # Page header
            page_header_with_actions(
                title="Inference Scanner",
                description="Perform inference scans on parts using deployed models",
                actions=[],
            ),
            # Success/Error messages
            rx.cond(
                InferenceState.success != "",
                success_message(InferenceState.success),
            ),
            rx.cond(
                InferenceState.error != "",
                error_message(InferenceState.error),
            ),
            # Two-column layout
            rx.grid(
                # Left column - Inference form
                rx.box(inference_form(), width="100%"),
                # Right column - Scan history
                rx.box(scan_history_table(), width="100%"),
                columns="2",
                gap="2rem",
                width="100%",
                align_items="start",
            ),
        ),
        width="100%",
        min_height="100vh",
        position="relative",
        # Initialize data on mount
        on_mount=InferenceState.on_mount,
    )


def inference_page() -> rx.Component:
    """
    Complete inference page with authentication wrapper.
    """
    return inference_content()
