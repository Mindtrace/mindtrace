from .select_input import select_input_with_form

def modern_select_field(
    label: str, placeholder: str, options, name: str = "", required: bool = False, size: str = "large"
):
    """Modern select field - using new select component. Supports size variants: small, medium, large (default)."""
    return select_input_with_form(
        label=label,
        placeholder=placeholder,
        items=options,
        name=name,
        required=required,
        size=size,
    )