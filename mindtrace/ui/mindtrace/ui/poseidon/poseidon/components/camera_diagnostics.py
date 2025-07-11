import reflex as rx
from poseidon.state.camera import CameraState


def camera_diagnostics() -> rx.Component:
    """Enhanced camera diagnostics component with better organization and design."""
    
    def status_badge(label: str, value: str, is_connected: bool = None) -> rx.Component:
        """Create a status badge with label and value."""
        return rx.hstack(
            rx.text(label, font_weight="500", color="#374151", width="140px", font_size="0.875rem"),
            rx.cond(
                is_connected is not None,
                rx.box(
                    rx.cond(
                        is_connected,
                        rx.text("🟢 Connected", font_size="0.875rem", color="white"),
                        rx.text("🔴 Disconnected", font_size="0.875rem", color="white")
                    ),
                    background=rx.cond(
                        is_connected,
                        "#059669",
                        "#DC2626"
                    ),
                    padding="0.25rem 0.5rem",
                    border_radius="4px",
                ),
                rx.text(value, color="#111827", font_size="0.875rem"),
            ),
            spacing="4",
            align="center",
            width="100%",
            padding="0.75rem 0",
            border_bottom="1px solid #F3F4F6",
        )
    
    def info_row(label: str, value: str) -> rx.Component:
        """Create an info row with label and value."""
        return rx.hstack(
            rx.text(label, font_weight="500", color="#374151", width="140px", font_size="0.875rem"),
            rx.text(value, color="#111827", font_size="0.875rem"),
            spacing="4",
            align="center",
            width="100%",
            padding="0.75rem 0",
            border_bottom="1px solid #F3F4F6",
        )
    
    def range_info(label: str, min_val: float, max_val: float, unit: str = "") -> rx.Component:
        """Create range information display."""
        return rx.hstack(
            rx.text(label, font_weight="500", color="#374151", width="140px", font_size="0.875rem"),
            rx.text(
                f"{min_val} - {max_val} {unit}",
                color="#111827",
                font_size="0.875rem"
            ),
            spacing="4",
            align="center",
            width="100%",
            padding="0.75rem 0",
            border_bottom="1px solid #F3F4F6",
        )
    
    def diagnostics_content() -> rx.Component:
        """Main diagnostics content with organized sections."""
        return rx.vstack(
            # Connection Status
            rx.cond(
                CameraState.diagnostics.get("connected") != None,
                status_badge("Connection", "", CameraState.diagnostics.get("connected")),
            ),
            
            # Backend Info
            rx.cond(
                CameraState.diagnostics.get("backend") != None,
                info_row("Backend", CameraState.diagnostics.get("backend", "")),
            ),
            
            # Device Info
            rx.cond(
                CameraState.diagnostics.get("device_name") != None,
                info_row("Device", CameraState.diagnostics.get("device_name", "")),
            ),
            
            # Current Settings Section
            rx.cond(
                CameraState.diagnostics.get("current_exposure") != None,
                info_row("Exposure", f"{CameraState.diagnostics.get('current_exposure', '')} μs"),
            ),
            
            rx.cond(
                CameraState.diagnostics.get("current_gain") != None,
                info_row("Gain", str(CameraState.diagnostics.get("current_gain", ""))),
            ),
            
            rx.cond(
                CameraState.diagnostics.get("current_pixel_format") != None,
                info_row("Pixel Format", CameraState.diagnostics.get("current_pixel_format", "")),
            ),
            
            # Range Information Section
            rx.cond(
                rx.cond(
                    CameraState.selected_camera != "",
                    rx.cond(
                        CameraState.camera_ranges.get(CameraState.selected_camera, {}).get("exposure") != None,
                        True,
                        False
                    ),
                    False
                ),
                range_info(
                    "Exposure Range",
                    CameraState.camera_ranges.get(CameraState.selected_camera, {}).get("exposure", [])[0],
                    CameraState.camera_ranges.get(CameraState.selected_camera, {}).get("exposure", [])[1],
                    "μs"
                ),
            ),
            
            rx.cond(
                rx.cond(
                    CameraState.selected_camera != "",
                    rx.cond(
                        CameraState.camera_ranges.get(CameraState.selected_camera, {}).get("gain") != None,
                        True,
                        False
                    ),
                    False
                ),
                range_info(
                    "Gain Range",
                    CameraState.camera_ranges.get(CameraState.selected_camera, {}).get("gain", [])[0],
                    CameraState.camera_ranges.get(CameraState.selected_camera, {}).get("gain", [])[1],
                ),
            ),
            
            spacing="0",
            width="100%",
        )
    
    def empty_state() -> rx.Component:
        """Empty state when no diagnostics are available."""
        return rx.center(
            rx.vstack(
                rx.box(
                    "📊",
                    font_size="3rem",
                    color="#9CA3AF",
                    margin_bottom="1rem",
                ),
                rx.text(
                    "No Diagnostics",
                    font_size="1.25rem",
                    font_weight="500",
                    color="#374151",
                ),
                rx.text(
                    "Select a camera to view its diagnostic information",
                    color="#6B7280",
                    text_align="center",
                    font_size="0.875rem",
                ),
                spacing="3",
                align="center",
            ),
            padding="3rem",
        )
    
    return rx.cond(
        CameraState.diagnostics != {},
        rx.vstack(
            # Header
            rx.hstack(
                rx.box(
                    "📊",
                    font_size="1.25rem",
                    color="#374151",
                    padding="0.5rem",
                    background="#F9FAFB",
                    border_radius="6px",
                ),
                rx.vstack(
                    rx.text(
                        "Camera Diagnostics",
                        font_weight="600",
                        font_size="1.125rem",
                        color="#111827",
                    ),
                    rx.text(
                        "Real-time camera health and settings",
                        font_size="0.875rem",
                        color="#6B7280",
                    ),
                    spacing="1",
                    align="start",
                ),
                spacing="3",
                align="center",
                margin_bottom="1.5rem",
            ),
            # Content
            diagnostics_content(),
            spacing="0",
            width="100%",
            align="stretch",
        ),
        empty_state(),
    ) 