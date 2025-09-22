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
        
        # File path input section
        rx.box(
            rx.text(
                "File Path:",
                font_weight="500",
                color=colors["gray_700"],
                margin_bottom=spacing["xs"],
            ),
            rx.input(
                placeholder="/path/to/config.json",
                value=CameraState.config_file_path,
                on_change=CameraState.set_config_file_path,
                width="100%",
                size="3",
            ),
            margin_bottom=spacing["md"],
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
        
        # Action buttons with consistent spacing
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
                    CameraState.selected_camera, 
                    CameraState.config_file_path
                ),
                disabled=(CameraState.selected_camera == "") | (CameraState.config_file_path == "") | CameraState.config_export_loading,
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
                    CameraState.selected_camera,
                    CameraState.config_file_path
                ),
                disabled=(CameraState.selected_camera == "") | (CameraState.config_file_path == "") | CameraState.config_import_loading,
                variant="solid",
                size="3",
            ),
            
            gap=spacing["md"],
            width="100%",
            flex_wrap="wrap",
        ),
        
        # Instructions with consistent styling
        rx.box(
            rx.text(
                "How to use:",
                font_weight="500",
                color=colors["gray_700"],
                margin_bottom=spacing["xs"],
            ),
            rx.box(
                "• Enter full path for config file location\n"
                "• Select an initialized camera from dropdown\n" 
                "• Export saves current camera settings to file\n"
                "• Import loads previously saved configuration",
                font_size="0.875rem",
                color=colors["gray_600"],
                line_height="1.5",
                white_space="pre-line",
            ),
            background=colors["gray_50"],
            border=f"1px solid {colors['border']}",
            border_radius=css_spacing["md"],
            padding=spacing["md"],
            margin_top=spacing["lg"],
        ),
        
        # Match existing card styling
        background=colors["white"],
        border=f"1px solid {colors['border']}",
        border_radius=css_spacing["lg"],
        padding=css_spacing["lg"],
        width="100%",
    )