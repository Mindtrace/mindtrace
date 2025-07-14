import reflex as rx
from poseidon.state.camera import CameraState


def camera_config_modal() -> rx.Component:
    """Simplified camera configuration modal with exposure and gain only."""
    
    def exposure_slider() -> rx.Component:
        """Simple log-scale exposure slider using state Vars."""
        return rx.vstack(
            rx.hstack(
                rx.text("Exposure (μs)", font_size="0.95rem", font_weight="600", color="#374151"),
                rx.hstack(
                    rx.text(CameraState.exposure_min_value, font_size="0.85rem", color="#6B7280"),
                    rx.text("–", font_size="0.85rem", color="#6B7280"),
                    rx.text(CameraState.exposure_max_value, font_size="0.85rem", color="#6B7280"),
                    spacing="1",
                ),
                rx.text("Current:", font_size="0.85rem", color="#6B7280"),
                rx.text(CameraState.exposure_display_value, font_size="0.85rem", color="#2563EB", font_weight="600"),
                spacing="3", align="center", width="100%", justify="between",
            ),
            rx.slider(
                min_value=0,
                max_value=100,
                value=[CameraState.exposure_slider_value],
                on_change=lambda v: CameraState.set_exposure_from_slider(v[0]),
                width="100%",
            ),
            spacing="2", align="start", width="100%",
        )

    def gain_slider() -> rx.Component:
        """Gain slider with dynamic range and current value display."""
        ranges = CameraState.current_camera_ranges
        gain_range = ranges.get("gain", [0, 24])
        min_gain = rx.cond(gain_range.length() > 0, gain_range[0], 0)
        max_gain = rx.cond(gain_range.length() > 1, gain_range[1], 24)
        current_gain = CameraState.camera_config.get("gain", 0)
        return rx.vstack(
            rx.hstack(
                rx.text("Gain", font_size="0.95rem", font_weight="600", color="#374151"),
                rx.hstack(
                    rx.text(min_gain, font_size="0.85rem", color="#6B7280"),
                    rx.text("–", font_size="0.85rem", color="#6B7280"),
                    rx.text(max_gain, font_size="0.85rem", color="#6B7280"),
                    spacing="1",
                ),
                rx.text("Current:", font_size="0.85rem", color="#6B7280"),
                rx.text(current_gain, font_size="0.85rem", color="#2563EB", font_weight="600"),
                spacing="3", align="center", width="100%", justify="between",
            ),
            rx.slider(
                min_value=min_gain,
                max_value=max_gain,
                value=[current_gain],
                on_change=lambda v: CameraState.update_config_value("gain", v[0]),
                width="100%",
            ),
            spacing="2", align="start", width="100%",
        )

    def image_display() -> rx.Component:
        """Image display section for captured images."""
        return rx.vstack(
            rx.text(
                "Captured Image",
                font_size="1rem",
                font_weight="600",
                color="#374151",
                margin_top="1rem",
            ),
            rx.cond(
                CameraState.capture_image_data,
                rx.center(
                    rx.box(
                        rx.image(
                            src="data:image/jpeg;base64," + CameraState.capture_image_data,
                            max_width="100%",
                            max_height="300px",
                            border_radius="8px",
                            border="1px solid #E5E7EB",
                            alt="Captured camera image",
                            object_fit="contain",
                        ),
                        background="white",
                        padding="1rem",
                        border_radius="8px",
                        box_shadow="0 2px 4px rgba(0, 0, 0, 0.1)",
                        width="100%",
                    ),
                    width="100%",
                ),
                rx.center(
                    rx.vstack(
                        rx.text(
                            "📸",
                            font_size="2rem",
                            color="#9CA3AF",
                        ),
                        rx.text(
                            "No image captured yet",
                            font_size="0.875rem",
                            color="#6B7280",
                        ),
                        spacing="2",
                        align="center",
                    ),
                    padding="2rem",
                    width="100%",
                ),
            ),
            spacing="2",
            width="100%",
        )

    def action_buttons() -> rx.Component:
        """Action buttons with loading states."""
        return rx.hstack(
            rx.dialog.close(
                rx.button(
                    "Cancel",
                    variant="surface",
                    color_scheme="gray",
                    cursor="pointer",
                )
            ),
            rx.cond(
                CameraState.capture_loading,
                rx.spinner(size="2", color="#059669"),
                rx.button(
                    "Capture Image",
                    variant="solid",
                    color_scheme="green",
                    cursor="pointer",
                    on_click=CameraState.capture_image,
                )
            ),
            spacing="3",
            justify="end",
            width="100%",
        )

    def camera_header() -> rx.Component:
        """Header with camera icon, name, and status."""
        return rx.hstack(
            rx.box(
                "📷",
                font_size="2rem",
                padding="0.75rem",
                background="#F9FAFB",
                border_radius="8px",
                border="1px solid #E5E7EB",
            ),
            rx.vstack(
                rx.text(
                    CameraState.selected_camera,
                    font_weight="700",
                    font_size="1.2rem",
                    color="#111827",
                ),
                rx.text(
                    "Configure camera settings",
                    font_size="0.95rem",
                    color="#6B7280",
                ),
                spacing="1",
                align="start",
            ),
            spacing="3",
            align="center",
            width="100%",
            padding="1rem",
            background="#F9FAFB",
            border_radius="8px",
            margin_bottom="1rem",
        )

    return rx.dialog.root(
        rx.dialog.trigger(
            rx.box(),  # Invisible trigger - modal is controlled by state
        ),
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.text("Camera Configuration", size="6", weight="bold"),
                    rx.dialog.close(rx.icon(tag="x", size=20, cursor="pointer")),
                    width="100%",
                    align="center",
                    justify="between",
                ),
                camera_header(),
                exposure_slider(),
                gain_slider(),
                image_display(),
                action_buttons(),
                spacing="5",
                align="stretch",
                width="100%",
            ),
            max_width="500px",
        ),
        open=CameraState.config_modal_open,
        on_open_change=lambda open: CameraState.set_config_modal_open(open),
    ) 