"""Camera configuration modal component."""

import reflex as rx

from ..state.camera_state import CameraState
from ..styles.theme import colors, css_spacing, radius, spacing


def camera_modal() -> rx.Component:
    """Configuration modal for camera settings."""

    def modal_header() -> rx.Component:
        """Modal header with title and close button."""
        return rx.hstack(
            rx.heading(
                f"Configure {CameraState.selected_camera}",
                size="6",
                color=colors["gray_900"],
            ),
            rx.spacer(),
            rx.button(
                rx.icon("x"),
                variant="ghost",
                size="2",
                on_click=CameraState.close_config_modal,
            ),
            width="100%",
            align="center",
            padding_bottom=css_spacing["md"],
            border_bottom=f"1px solid {colors['border']}",
            margin_bottom=css_spacing["lg"],
        )

    def exposure_control() -> rx.Component:
        """Exposure time control with slider."""
        return rx.vstack(
            rx.hstack(
                rx.text(
                    "Exposure Time (μs)",
                    font_weight="500",
                    color=colors["gray_700"],
                ),
                rx.spacer(),
                rx.text(
                    f"{CameraState.config_exposure} μs",
                    font_weight="600",
                    color=colors["primary"],
                    font_size="0.875rem",
                ),
                width="100%",
                align="center",
            ),
            rx.slider(
                min=CameraState.exposure_min_microseconds,
                max=CameraState.exposure_max_microseconds,
                step=100,
                value=[CameraState.config_exposure],
                on_change=lambda value: CameraState.set_config_exposure(value[0]),
                width="100%",
                color_scheme="blue",
            ),
            rx.hstack(
                rx.text(
                    f"{CameraState.exposure_min_microseconds} μs",
                    font_size="0.75rem",
                    color=colors["gray_500"],
                ),
                rx.spacer(),
                rx.text(
                    f"{CameraState.exposure_max_microseconds} μs",
                    font_size="0.75rem",
                    color=colors["gray_500"],
                ),
                width="100%",
            ),
            spacing=spacing["sm"],
            align="start",
            width="100%",
        )

    def gain_control() -> rx.Component:
        """Gain control with slider."""
        return rx.vstack(
            rx.hstack(
                rx.text(
                    "Gain (dB)",
                    font_weight="500",
                    color=colors["gray_700"],
                ),
                rx.spacer(),
                rx.text(
                    f"{CameraState.config_gain} dB",
                    font_weight="600",
                    color=colors["primary"],
                    font_size="0.875rem",
                ),
                width="100%",
                align="center",
            ),
            rx.slider(
                min=rx.cond(
                    CameraState.config_ranges_for_selected.get("gain", []).length() >= 2,
                    CameraState.config_ranges_for_selected.get("gain", [])[0],
                    0,
                ),
                max=rx.cond(
                    CameraState.config_ranges_for_selected.get("gain", []).length() >= 2,
                    CameraState.config_ranges_for_selected.get("gain", [])[1],
                    30,
                ),
                step=1,
                value=[CameraState.config_gain],
                on_change=lambda value: CameraState.set_config_gain(value[0]),
                width="100%",
                color_scheme="blue",
            ),
            rx.hstack(
                rx.text(
                    rx.cond(
                        CameraState.config_ranges_for_selected.get("gain", []).length() >= 2,
                        f"{CameraState.config_ranges_for_selected.get('gain', [])[0]} dB",
                        "0 dB",
                    ),
                    font_size="0.75rem",
                    color=colors["gray_500"],
                ),
                rx.spacer(),
                rx.text(
                    rx.cond(
                        CameraState.config_ranges_for_selected.get("gain", []).length() >= 2,
                        f"{CameraState.config_ranges_for_selected.get('gain', [])[1]} dB",
                        "30 dB",
                    ),
                    font_size="0.75rem",
                    color=colors["gray_500"],
                ),
                width="100%",
            ),
            spacing=spacing["sm"],
            align="start",
            width="100%",
        )

    def trigger_mode_control() -> rx.Component:
        """Trigger mode control with dynamic options from camera capabilities."""
        return rx.vstack(
            rx.text(
                "Trigger Mode",
                font_weight="500",
                color=colors["gray_700"],
            ),
            rx.select(
                CameraState.available_trigger_modes,
                value=CameraState.config_trigger_mode,
                on_change=CameraState.set_config_trigger_mode,
                width="100%",
            ),
            rx.text(
                f"Current: {CameraState.config_trigger_mode}",
                font_size="0.875rem",
                color=colors["gray_500"],
            ),
            spacing=spacing["sm"],
            align="start",
            width="100%",
        )

    def file_import_export_section() -> rx.Component:
        """File import/export section for camera configuration."""
        return rx.vstack(
            # Section header
            rx.text(
                "Import/Export Configuration",
                font_weight="600",
                color=colors["gray_800"],
                font_size="1rem",
                margin_bottom=spacing["sm"],
            ),
            # Upload area
            rx.upload(
                rx.vstack(
                    rx.icon("cloud-upload", size=32, color=colors["gray_400"]),
                    rx.text(
                        "Drop JSON config or click to browse",
                        color=colors["gray_600"],
                        font_size="0.875rem",
                        text_align="center",
                    ),
                    spacing=spacing["sm"],
                    align="center",
                    justify="center",
                    width="100%",
                    height="120px",
                    border=f"2px dashed {colors['border']}",
                    border_radius=css_spacing["md"],
                    padding=css_spacing["lg"],
                    background=colors["gray_50"],
                    cursor="pointer",
                    _hover={
                        "border_color": colors["primary"],
                        "background": colors["primary"] + "10",
                    },
                ),
                id="modal_config_upload",
                accept={"application/json": [".json"]},
                max_files=1,
                on_drop=CameraState.handle_upload(rx.upload_files("modal_config_upload")),
            ),
            # Show selected files from upload component
            rx.cond(
                rx.selected_files("modal_config_upload").length() > 0,
                rx.vstack(
                    rx.text(
                        "Selected files:",
                        font_size="0.75rem",
                        color=colors["gray_500"],
                        font_weight="500",
                    ),
                    rx.foreach(
                        rx.selected_files("modal_config_upload"),
                        lambda file: rx.hstack(
                            rx.icon("file-json", size=16, color=colors["primary"]),
                            rx.text(
                                file,
                                font_size="0.875rem",
                                color=colors["gray_700"],
                            ),
                            align="center",
                            padding=spacing["xs"],
                            background=colors["white"],
                            border_radius=css_spacing["sm"],
                            border=f"1px solid {colors['border']}",
                            width="100%",
                        ),
                    ),
                    spacing=spacing["xs"],
                    width="100%",
                ),
            ),
            # Show uploaded file if any
            rx.cond(
                CameraState.selected_file != "",
                rx.hstack(
                    rx.icon("file-json", size=16, color=colors["success"]),
                    rx.text(
                        "Uploaded: " + CameraState.selected_file,
                        font_size="0.875rem",
                        color=colors["gray_700"],
                        font_weight="500",
                    ),
                    rx.button(
                        rx.icon("x", size=14),
                        variant="ghost",
                        size="1",
                        on_click=lambda: CameraState.set_selected_file(""),
                    ),
                    align="center",
                    padding=spacing["sm"],
                    background=colors["success"] + "10",
                    border_radius=css_spacing["sm"],
                    border=f"1px solid {colors['success']}30",
                    width="100%",
                ),
            ),
            # Action buttons
            rx.hstack(
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
                            "Export",
                            align="center",
                            gap=spacing["xs"],
                        ),
                    ),
                    on_click=lambda: CameraState.export_camera_config(CameraState.selected_camera),
                    disabled=CameraState.config_export_loading,
                    variant="outline",
                    size="2",
                    flex="1",
                ),
                rx.button(
                    "Upload",
                    on_click=lambda: CameraState.handle_upload(rx.upload_files("modal_config_upload")),
                    variant="outline",
                    size="2",
                    flex="1",
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
                            "Import",
                            align="center",
                            gap=spacing["xs"],
                        ),
                    ),
                    on_click=lambda: CameraState.import_camera_config(CameraState.selected_camera),
                    disabled=(CameraState.selected_file == "") | CameraState.config_import_loading,
                    variant="solid",
                    size="2",
                    flex="1",
                ),
                width="100%",
                spacing=spacing["sm"],
                justify="center",
            ),
            spacing=spacing["md"],
            width="100%",
            padding=spacing["md"],
            background=colors["gray_50"],
            border_radius=css_spacing["md"],
            border=f"1px solid {colors['border']}",
        )

    def modal_footer() -> rx.Component:
        """Modal footer with action buttons."""
        return rx.hstack(
            rx.button(
                "Cancel",
                variant="outline",
                size="3",
                on_click=CameraState.close_config_modal,
            ),
            rx.button(
                "Apply Configuration",
                variant="solid",
                size="3",
                color_scheme="blue",
                on_click=CameraState.apply_camera_config,
            ),
            spacing=spacing["md"],
            justify="end",
            width="100%",
            padding_top=css_spacing["lg"],
            border_top=f"1px solid {colors['border']}",
        )

    def modal_content() -> rx.Component:
        """Main modal content."""
        return rx.vstack(
            modal_header(),
            rx.vstack(
                rx.cond(
                    CameraState.exposure_supported,
                    exposure_control(),
                    rx.fragment(),  # Show nothing if exposure not supported
                ),
                gain_control(),
                trigger_mode_control(),
                spacing=spacing["lg"],
                width="100%",
            ),
            # Add file import/export section
            file_import_export_section(),
            modal_footer(),
            spacing=spacing["lg"],
            width="100%",
            max_width="600px",
        )

    return rx.dialog.root(
        rx.dialog.content(
            modal_content(),
            background=colors["white"],
            border_radius=radius["lg"],
            box_shadow="0 25px 50px -12px rgba(0, 0, 0, 0.25)",
            padding=css_spacing["xl"],
            max_width="600px",
            width="90vw",
        ),
        open=CameraState.config_modal_open,
    )


def status_banner() -> rx.Component:
    """Status banner for displaying messages."""

    def message_icon() -> rx.Component:
        """Icon based on message type."""
        return rx.cond(
            CameraState.message_type == "success",
            rx.icon("check", color=colors["success"]),
            rx.cond(
                CameraState.message_type == "error",
                rx.icon("x", color=colors["error"]),
                rx.cond(
                    CameraState.message_type == "warning",
                    rx.icon("triangle-alert", color=colors["warning"]),
                    rx.icon("info", color=colors["info"]),
                ),
            ),
        )

    def banner_style() -> dict:
        """Get banner style based on message type."""
        return rx.cond(
            CameraState.message_type == "success",
            {
                "background": colors["success"] + "10",
                "border": f"1px solid {colors['success']}30",
                "color": colors["success"],
            },
            rx.cond(
                CameraState.message_type == "error",
                {
                    "background": colors["error"] + "10",
                    "border": f"1px solid {colors['error']}30",
                    "color": colors["error"],
                },
                rx.cond(
                    CameraState.message_type == "warning",
                    {
                        "background": colors["warning"] + "10",
                        "border": f"1px solid {colors['warning']}30",
                        "color": colors["warning"],
                    },
                    {
                        "background": colors["info"] + "10",
                        "border": f"1px solid {colors['info']}30",
                        "color": colors["info"],
                    },
                ),
            ),
        )

    return rx.cond(
        CameraState.message != "",
        rx.box(
            rx.hstack(
                message_icon(),
                rx.text(
                    CameraState.message,
                    font_weight="500",
                ),
                rx.spacer(),
                rx.button(
                    rx.icon("x", size=16),
                    variant="ghost",
                    size="1",
                    on_click=CameraState.clear_message,
                ),
                spacing=spacing["md"],
                align="center",
                width="100%",
            ),
            **banner_style(),
            border_radius=radius["md"],
            padding=spacing["md"],
            margin_bottom=spacing["lg"],
        ),
    )
