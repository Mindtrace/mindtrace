"""Mindtrace Card Components - Modern Glass Morphism Cards."""

import reflex as rx


def card_mindtrace(children, **kwargs) -> rx.Component:
    """
    Ultra-modern glass morphism card.
    """
    return rx.box(
        rx.vstack(
            *children,
            spacing="0",
            width="100%",
        ),
        style={
            "background": "rgba(255, 255, 255, 0.95)",
            "backdrop_filter": "blur(20px)",
            "border_radius": "24px",
            "border": "1px solid rgba(255, 255, 255, 0.2)",
            "box_shadow": """
                0 8px 32px rgba(0, 0, 0, 0.08),
                0 2px 8px rgba(0, 0, 0, 0.04),
                inset 0 1px 0 rgba(255, 255, 255, 0.5)
            """,
            "padding": "2rem",
            "width": "100%",
            "position": "relative",
            "overflow": "hidden",
            "animation": "slideInUp 0.8s cubic-bezier(0.4, 0, 0.2, 1)",
            "_before": {
                "content": "''",
                "position": "absolute",
                "top": "0",
                "left": "0",
                "right": "0",
                "height": "4px",
                "background": "linear-gradient(90deg, #0057FF, #0041CC, #0066FF, #0057FF)",
                "background_size": "200% 100%",
                "animation": "shimmer 3s ease-in-out infinite",
            }
        },
        **kwargs
    ) 