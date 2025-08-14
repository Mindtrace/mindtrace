"""Mindtrace Card Components - Modern Glass Morphism Cards."""

import reflex as rx

from poseidon.styles.global_styles import C
from poseidon.styles.variants import COMPONENT_VARIANTS


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
            **COMPONENT_VARIANTS["card"]["base"],
            "animation": "slideInUp 0.8s cubic-bezier(0.4, 0, 0.2, 1)",
            "_before": {
                "content": "''",
                "position": "absolute",
                "top": "0",
                "left": "0",
                "right": "0",
                "height": "4px",
                "background": f"linear-gradient(90deg, {C.accent}, {C.ring}, {C.accent}, {C.accent})",
                "background_size": "200% 100%",
                "animation": "shimmer 3s ease-in-out infinite",
            },
        },
        **kwargs,
    )
