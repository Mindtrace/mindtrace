from .text_input import text_input_with_form

def form_input_with_label(
    label: str, placeholder: str, input_type: str = "text", name: str = "", required: bool = False, size: str = "large"
):
    """Form input with label - using mindtrace styling. Supports size variants: small, medium, large (default)."""
    return text_input_with_form(
        label=label,
        placeholder=placeholder,
        name=name,
        input_type=input_type,
        required=required,
        size=size,
    )