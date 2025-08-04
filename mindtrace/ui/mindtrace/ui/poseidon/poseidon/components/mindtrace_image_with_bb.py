"""
Poseidon Mindtrace Image with Bounding Box Component

This component displays an image with an overlay of bounding boxes
using mindtrace styling. It can be used to visualize detected objects
with their class labels.
"""

import reflex as rx
from .mindtrace_bb import mindtrace_bb as mindtrace_bb_component

# --- Mindtrace Image on dialog with bounding box ---
def mindtrace_image_with_bb(
    bb_component: rx.Component,
    image: rx.image,
    text: str = "",
) -> rx.Component:

    title = rx.hstack(
        rx.text(text, size="6", weight="bold"),
        rx.dialog.close(rx.icon(tag="x", size=20, cursor="pointer")),
        width="100%",
        align="center",
        justify="between",
    )

    return rx.dialog.root(
        rx.dialog.content(
            title,
            rx.dialog.body(
                rx.box(
                    rx.image(
                        src=image.src,
                        width=image.width,
                        height=image.height,
                        alt=image.alt,
                        position="absolute",
                        top="0",
                        left="0",
                    ),
                    bb_component,
                    width=image.width,
                    height=image.height,
                    position="relative",
                    overflow="hidden",
                ),
                display="flex",
                align_items="center",
                justify_content="center",
            ),
        )
    )
