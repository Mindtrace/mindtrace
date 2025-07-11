import reflex as rx
from poseidon.state.camera import CameraState
from poseidon.components.camera_config_modal import camera_config_modal


def camera_card(camera: str) -> rx.Component:
    """Modular camera card component with status, info, and actions."""
    
    def camera_info_section() -> rx.Component:
        """Camera information display with icon, name, and status."""
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
                    rx.cond(
                        camera.contains(":"),
                        camera.split(":")[1],
                        camera
                    ),
                    font_weight="600",
                    font_size="1.1rem",
                    color="#111827",
                ),
                rx.text(
                    rx.cond(
                        camera.contains(":"),
                        camera.split(":")[0],
                        "Unknown"
                    ),
                    font_size="0.875rem",
                    color="#6B7280",
                ),
                # Status badge
                rx.box(
                    rx.text(
                        CameraState.camera_status_badges[camera],
                        font_size="0.75rem",
                        font_weight="500",
                        color="white",
                    ),
                    background=CameraState.camera_status_colors[camera],
                    padding="0.25rem 0.5rem",
                    border_radius="4px",
                    margin_top="0.5rem",
                ),
                spacing="1",
                align="start",
            ),
            spacing="3",
            align="center",
            width="100%",
        )
    
    def action_buttons() -> rx.Component:
        """Action buttons for camera initialization and configuration."""
        return rx.vstack(
            # Initialize button (always visible)
            rx.button(
                "Initialize",
                variant="solid",
                color_scheme="blue",
                size="2",
                on_click=lambda name=camera: CameraState.initialize_camera(name),
                width="100%",
                _hover={"transform": "translateY(-1px)", "box_shadow": "0 4px 8px rgba(0, 0, 0, 0.15)"},
                transition="all 0.2s ease",
            ),
            # Configure button (only if initialized)
            rx.cond(
                CameraState.camera_statuses.get(camera, "not_initialized") == "initialized",
                camera_config_modal(camera),
                rx.box(height="40px"),  # Placeholder to maintain consistent card height
            ),
            spacing="2",
            width="100%",
            align="stretch",
        )
    
    return rx.box(
        rx.vstack(
            camera_info_section(),
            action_buttons(),
            spacing="4",
            width="100%",
            align="stretch",
        ),
        background="white",
        border="1px solid #E5E7EB",
        border_radius="12px",
        padding="1.5rem",
        box_shadow="0 1px 3px rgba(0, 0, 0, 0.1)",
        _hover={
            "box_shadow": "0 8px 25px rgba(0, 0, 0, 0.15)",
            "border_color": "#D1D5DB",
            "transform": "translateY(-2px)",
        },
        transition="all 0.3s ease",
        width="100%",
        min_height="200px",  # Ensure consistent card height
        display="flex",
        flex_direction="column",
    ) 