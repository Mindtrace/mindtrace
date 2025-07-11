import reflex as rx
from poseidon.state.camera import CameraState


def image_display() -> rx.Component:
    """Enhanced image display component with better design and functionality."""
    
    def image_content() -> rx.Component:
        """Main image content with display and download functionality."""
        return rx.vstack(
            # Header
            rx.hstack(
                rx.box(
                    "📸",
                    font_size="1.25rem",
                    color="#374151",
                    padding="0.5rem",
                    background="#F9FAFB",
                    border_radius="6px",
                ),
                rx.vstack(
                    rx.text(
                        "Captured Image",
                        font_weight="600",
                        font_size="1.125rem",
                        color="#111827",
                    ),
                    rx.text(
                        "View and download captured images",
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
            
            # Image display
            rx.center(
                rx.box(
                    rx.image(
                        src=rx.cond(
                            CameraState.capture_image_data,
                            "data:image/jpeg;base64," + CameraState.capture_image_data,
                            ""
                        ),
                        max_width="100%",
                        max_height="400px",
                        border_radius="12px",
                        border="1px solid #E5E7EB",
                        alt="Captured camera image",
                        object_fit="contain",
                    ),
                    background="white",
                    padding="1rem",
                    border_radius="12px",
                    box_shadow="0 4px 6px rgba(0, 0, 0, 0.1)",
                    width="100%",
                ),
                width="100%",
            ),
            
            # Download button
            rx.center(
                rx.button(
                    rx.hstack(
                        rx.text("📥", font_size="1rem"),
                        rx.text("Download Image", font_weight="500"),
                        spacing="2",
                        align="center",
                    ),
                    on_click=rx.download(
                        data=CameraState.capture_image_data,
                        filename=rx.cond(
                            CameraState.selected_camera != "",
                            "camera_capture_" + CameraState.selected_camera + ".jpg",
                            "camera_capture.jpg"
                        )
                    ),
                    background="#111827",
                    color="white",
                    border="none",
                    padding="0.75rem 1.5rem",
                    border_radius="8px",
                    font_size="0.875rem",
                    font_weight="500",
                    margin_top="1.5rem",
                    _hover={
                        "background": "#374151",
                        "transform": "translateY(-1px)",
                        "box_shadow": "0 4px 8px rgba(0, 0, 0, 0.2)",
                    },
                    transition="all 0.2s ease",
                ),
                width="100%",
            ),
            
            spacing="0",
            width="100%",
            align="stretch",
        )
    
    def empty_state() -> rx.Component:
        """Empty state when no image is captured."""
        return rx.center(
            rx.vstack(
                rx.box(
                    "📸",
                    font_size="3rem",
                    color="#9CA3AF",
                    margin_bottom="1rem",
                ),
                rx.text(
                    "No Image",
                    font_size="1.25rem",
                    font_weight="500",
                    color="#374151",
                ),
                rx.text(
                    "Capture an image to see it here",
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
        CameraState.capture_image_data,
        image_content(),
        empty_state(),
    ) 