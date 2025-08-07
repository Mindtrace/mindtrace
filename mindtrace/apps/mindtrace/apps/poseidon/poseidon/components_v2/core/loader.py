"""Loader Component for PAZ"""

import reflex as rx
from poseidon.styles.variants import COMPONENT_VARIANTS


def loader(
    size: str = "medium",
    variant: str = "primary",
    **kwargs
) -> rx.Component:
    """
    Simple spinning loader component.
    Supports size variants: small, medium, large
    Supports color variants: primary, secondary, danger, success
    """
    # Get size from SIZE_VARIANTS or use default
    size_map = {
        "small": "1rem",
        "medium": "2rem", 
        "large": "3rem"
    }
    
    current_size = size_map.get(size, size_map["medium"])
    
    # Get color from COMPONENT_VARIANTS or use primary as default
    loader_variant = COMPONENT_VARIANTS["loader"].get(variant, COMPONENT_VARIANTS["loader"]["primary"])
    current_color = loader_variant["color"]
    
    return rx.box(
        rx.el.div(
            style={
                "width": current_size,
                "height": current_size,
                "border": f"3px solid {current_color}20",  # 20 = 12% opacity
                "border_top": f"3px solid {current_color}",
                "border_radius": "50%",
                "animation": "spin 1s linear infinite",
            }
        ),
        style={
            "display": "flex",
            "align_items": "center", 
            "justify_content": "center",
            "min_height": "100vh",
            "width": "100vw",
            "position": "fixed",
            "top": "0",
            "left": "0",
            "z_index": "9999",
        },
        **kwargs
    ) 