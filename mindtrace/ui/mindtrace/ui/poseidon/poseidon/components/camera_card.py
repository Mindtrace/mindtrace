import reflex as rx
from poseidon.state.camera import CameraState
from poseidon.components.mindtrace_cards import card_mindtrace


def camera_card(camera: str) -> rx.Component:
    """Simplified camera card using mindtrace card component."""
    
    def camera_header() -> rx.Component:
        """Camera header with icon, name, and status."""
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
        """Action buttons for camera initialization, deinitialization, and configuration."""
        return rx.vstack(
            # Initialize/Deinitialize button (conditional based on status)
            rx.cond(
                CameraState.camera_statuses.get(camera, "not_initialized") == "available",
                # Camera is available - show Deinitialize button (red)
                rx.button(
                    "Deinitialize",
                    variant="solid",
                    color_scheme="red",
                    size="2",
                    on_click=lambda name=camera: CameraState.close_camera(name),
                    width="100%",
                    _hover={"transform": "translateY(-1px)", "box_shadow": "0 4px 8px rgba(0, 0, 0, 0.15)"},
                    transition="all 0.2s ease",
                ),
                # Camera is not available - show Initialize button (blue)
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
            ),
            # Configure button (only if available)
            rx.cond(
                CameraState.camera_statuses.get(camera, "not_initialized") == "available",
                rx.button(
                    "Configure",
                    variant="solid",
                    color_scheme="green",
                    size="2",
                    width="100%",
                    on_click=lambda name=camera: CameraState.open_camera_config(name),
                    _hover={"transform": "translateY(-1px)", "box_shadow": "0 4px 8px rgba(0, 0, 0, 0.15)"},
                    transition="all 0.2s ease",
                ),
                rx.box(height="40px"),  # Placeholder to maintain consistent card height
            ),
            spacing="2",
            width="100%",
            align="stretch",
        )
    
    return card_mindtrace(
        children=[camera_header(), action_buttons()],
        width="100%",
        min_height="200px",
    ) 