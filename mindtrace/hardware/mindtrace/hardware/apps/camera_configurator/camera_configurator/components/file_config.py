"""File-based camera configuration component."""

import reflex as rx
from ..state.camera_state import CameraState
from ..styles.theme import colors, spacing, css_spacing


def file_config_section() -> rx.Component:
    """File-based configuration management section."""
    return rx.box(
        # Section header with icon
        rx.flex(
            rx.icon("folder-open", size=20, color=colors["primary"]),
            rx.text(
                "Configuration Files",
                font_weight="600",
                font_size="1.125rem",
                color=colors["gray_900"],
            ),
            align="center",
            gap=spacing["sm"],
            margin_bottom=spacing["md"],
        ),
        
        # Drag and drop upload area
        rx.box(
            rx.text(
                "Upload Configuration:",
                font_weight="500",
                color=colors["gray_700"],
                margin_bottom=spacing["xs"],
            ),
            rx.upload(
                rx.box(
                    rx.flex(
                        rx.icon("cloud-upload", size=32, color=colors["gray_400"]),
                        rx.vstack(
                            rx.text(
                                "Drag and drop JSON files here",
                                font_weight="500",
                                color=colors["gray_700"],
                                font_size="1rem",
                            ),
                            rx.text(
                                "or click to browse",
                                color=colors["gray_500"],
                                font_size="0.875rem",
                            ),
                            spacing="2",
                            align="center",
                        ),
                        direction="column",
                        align="center",
                        gap=spacing["sm"],
                    ),
                    border=f"2px dashed {colors['border']}",
                    border_radius=css_spacing["lg"],
                    padding=css_spacing["xl"],
                    background=colors["gray_50"],
                    width="100%",
                    min_height="120px",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                    cursor="pointer",
                    _hover={
                        "border_color": colors["primary"],
                        "background": colors["primary"] + "10",
                    },
                ),
                id="config_upload",
                accept={"application/json": [".json"]},
                multiple=True,
                max_files=10,
            ),
            rx.button(
                "Upload Files", 
                on_click=CameraState.handle_upload(rx.upload_files("config_upload")),
                margin_top=spacing["sm"],
            ),
            margin_bottom=spacing["md"],
        ),
        
        # Show uploaded files with selector
        rx.cond(
            CameraState.uploaded_files.length() > 0,
            rx.box(
                rx.text(
                    "Select File for Import:",
                    font_weight="500",
                    color=colors["gray_700"],
                    margin_bottom=spacing["xs"],
                ),
                rx.select(
                    CameraState.uploaded_files,
                    placeholder="Choose a file...",
                    value=CameraState.selected_file,
                    on_change=CameraState.set_selected_file,
                    width="100%",
                    size="3",
                ),
                margin_bottom=spacing["md"],
            ),
        ),
        
        # Camera selection for config operations
        rx.box(
            rx.text(
                "Camera:",
                font_weight="500", 
                color=colors["gray_700"],
                margin_bottom=spacing["xs"],
            ),
            rx.select(
                CameraState.cameras,
                placeholder="Select camera...",
                value=CameraState.selected_camera,
                on_change=CameraState.set_selected_camera,
                width="100%",
                size="3",
            ),
            margin_bottom=spacing["lg"],
        ),
        
        # Action buttons centered
        rx.flex(
            rx.button(
                rx.cond(
                    CameraState.config_export_loading,
                    rx.flex(
                        rx.spinner(size="1"),
                        "Exporting...",
                        align="center",
                        gap=spacing["xs"],
                    ),
                    rx.flex(
                        rx.icon("download", size=16),
                        "Export Config",
                        align="center",
                        gap=spacing["xs"],
                    )
                ),
                on_click=lambda: CameraState.export_camera_config(
                    CameraState.selected_camera
                ),
                disabled=(CameraState.selected_camera == "") | CameraState.config_export_loading,
                variant="outline",
                size="3",
            ),
            
            rx.button(
                rx.cond(
                    CameraState.config_import_loading,
                    rx.flex(
                        rx.spinner(size="1"),
                        "Importing...",
                        align="center",
                        gap=spacing["xs"],
                    ),
                    rx.flex(
                        rx.icon("upload", size=16),
                        "Import Config",
                        align="center",
                        gap=spacing["xs"],
                    )
                ),
                on_click=lambda: CameraState.import_camera_config(
                    CameraState.selected_camera
                ),
                disabled=(CameraState.selected_camera == "") | (CameraState.selected_file == "") | CameraState.config_import_loading,
                variant="solid",
                size="3",
            ),
            
            gap=spacing["md"],
            justify="center",
            width="100%",
            flex_wrap="wrap",
        ),
        
        
        # Match existing card styling
        background=colors["white"],
        border=f"1px solid {colors['border']}",
        border_radius=css_spacing["lg"],
        padding=css_spacing["lg"],
        width="100%",
    )