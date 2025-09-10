from poseidon.components_v2.core.button import button

def modern_button(text: str, button_type: str = "submit", size: str = "md", **kwargs):
    """Modern button - using mindtrace styling. Supports size variants: small, medium, large (default)."""
    return button(text=text, type=button_type, size=size, **kwargs)