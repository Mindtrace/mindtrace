import reflex as rx
from poseidon.state.camera import CameraState


def status_banner() -> rx.Component:
    """Enhanced status banner component for error and success messages."""
    
    def error_banner() -> rx.Component:
        """Error banner with warning icon and message."""
        return rx.box(
            rx.hstack(
                rx.box(
                    "⚠️",
                    font_size="1.25rem",
                    padding="0.5rem",
                    background="#FEF2F2",
                    border_radius="6px",
                ),
                rx.vstack(
                    rx.text(
                        "Error",
                        font_weight="600",
                        font_size="0.875rem",
                        color="#DC2626",
                    ),
                    rx.text(
                        CameraState.error,
                        font_weight="500",
                        font_size="0.875rem",
                        color="#DC2626",
                    ),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                rx.button(
                    "✕",
                    on_click=CameraState.clear_messages,
                    background="transparent",
                    color="#DC2626",
                    border="none",
                    font_size="1.25rem",
                    cursor="pointer",
                    _hover={"opacity": "0.7"},
                    transition="opacity 0.2s ease",
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            background="#FEF2F2",
            border="1px solid #FECACA",
            border_radius="12px",
            padding="1rem",
            margin_bottom="1rem",
            box_shadow="0 2px 4px rgba(220, 38, 38, 0.1)",
            animation="slideIn 0.3s ease-out",
        )
    
    def success_banner() -> rx.Component:
        """Success banner with checkmark icon and message."""
        return rx.box(
            rx.hstack(
                rx.box(
                    "✅",
                    font_size="1.25rem",
                    padding="0.5rem",
                    background="#F0FDF4",
                    border_radius="6px",
                ),
                rx.vstack(
                    rx.text(
                        "Success",
                        font_weight="600",
                        font_size="0.875rem",
                        color="#059669",
                    ),
                    rx.text(
                        CameraState.success,
                        font_weight="500",
                        font_size="0.875rem",
                        color="#059669",
                    ),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                rx.button(
                    "✕",
                    on_click=CameraState.clear_messages,
                    background="transparent",
                    color="#059669",
                    border="none",
                    font_size="1.25rem",
                    cursor="pointer",
                    _hover={"opacity": "0.7"},
                    transition="opacity 0.2s ease",
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            background="#F0FDF4",
            border="1px solid #BBF7D0",
            border_radius="12px",
            padding="1rem",
            margin_bottom="1rem",
            box_shadow="0 2px 4px rgba(5, 150, 105, 0.1)",
            animation="slideIn 0.3s ease-out",
        )
    
    return rx.vstack(
        rx.cond(
            CameraState.error != "",
            error_banner(),
        ),
        rx.cond(
            CameraState.success != "",
            success_banner(),
        ),
        spacing="0",
        width="100%",
    ) 