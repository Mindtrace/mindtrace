"""Button Component for PAZ"""

import reflex as rx
from poseidon.styles.global_styles import SIZE_VARIANTS
from poseidon.styles.variants import COMPONENT_VARIANTS


def button(
    text: str, 
    button_type: str = "submit", 
    variant: str = "primary",
    size: str = "large",
    **kwargs
) -> rx.Component:
    """
    Exceptional animated button with hover effects.
    Supports size variants: small, medium, large (default)
    """
    scheme = COMPONENT_VARIANTS["button"].get(variant, COMPONENT_VARIANTS["button"]["primary"])
    current_size = SIZE_VARIANTS["button"].get(size, SIZE_VARIANTS["button"]["large"])
    
    return rx.el.button(
        text,
        type=button_type,
        style={
            **COMPONENT_VARIANTS["button"]["base"],
            "padding": current_size["padding"],
            "font_size": current_size["font_size"],
            "background": scheme["background"],
            "box_shadow": scheme["shadow"],
            "_hover": {
                "transform": "translateY(-2px)",
                "box_shadow": scheme["hover_shadow"],
                "background": scheme["hover_background"],
            },
            "_active": {
                "transform": "translateY(0px)",
            },
            "_before": {
                "content": "''",
                "position": "absolute",
                "top": "0",
                "left": "-100%",
                "width": "100%",
                "height": "100%",
                "background": "linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent)",
                "transition": "left 0.6s ease",
            },
            "_hover::before": {
                "left": "100%",
            }
        },
        custom_attrs={"data-size": size},
        **kwargs
    )
