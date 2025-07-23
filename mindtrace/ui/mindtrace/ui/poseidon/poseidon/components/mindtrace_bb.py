"""
Poseidon Mindtrace Bounding Box Component

This component creates a bounding box with mindtrace styling.
It can be used to display detected objects with their class labels.
"""

import reflex as rx

def mindtrace_bb(
    det_x: float,
    det_y: float,
    det_w: float,
    det_h: float,
    det_cls: str,
    healthy: bool,
    title: str = "Bounding Box",
) -> rx.Component:
    """Create a bounding box with mindtrace styling."""
    return rx.el.canvas(
        rx.box(
            rx.text(det_cls, 
                background_color="red",
                color="white",
                font_size="12px",
                padding_x="4px",
                border_radius="2px",
                position="absolute",
                top=f"{det_y - 16}px",
                left=f"{det_x}px",
                z_index="2"
            ),
            rx.box(
                position="absolute",
                top=f"{det_y}px",
                left=f"{det_x}px",
                width=f"{det_w}px",
                height=f"{det_h}px",
                border="2px solid red",
                z_index="1"
            ),
            position="relative"
        ),
        width="100%",
        height="100%",
        position="relative"
    )
