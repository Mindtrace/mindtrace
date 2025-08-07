"""Text Input Component for Poseidon Forms"""

import reflex as rx
from typing import Optional, Callable, Any
from poseidon.styles.global_styles import COLORS, TYPOGRAPHY, SIZE_VARIANTS
from poseidon.styles.variants import COMPONENT_VARIANTS
from poseidon.components_v2.alerts import Alert

def text_input(
    label: Optional[str] = None,
    placeholder: Optional[str] = None,
    name: Optional[str] = None,
    value: Optional[str] = None,
    on_change: Optional[Callable] = None,
    on_blur: Optional[Callable] = None,
    on_focus: Optional[Callable] = None,
    input_type: str = "text",
    required: bool = False,
    disabled: bool = False,
    size: str = "large",
    error: bool = False,
    error_message: Optional[str] = None,
    success: bool = False,
    success_message: Optional[str] = None,
    hint: Optional[str] = None,
    **kwargs
) -> rx.Component:
    """
    Modern text input component with validation states and error handling.
    
    Args:
        label: Input label text
        placeholder: Placeholder text
        name: Input name attribute
        value: Current input value
        on_change: Callback for value changes
        on_blur: Callback for blur events
        on_focus: Callback for focus events
        input_type: HTML input type (text, email, password, etc.)
        required: Whether the input is required
        disabled: Whether the input is disabled
        size: Input size variant (small, medium, large)
        variant: Input variant (default, error, success)
        error: Whether to show error state
        error_message: Error message to display
        success: Whether to show success state
        success_message: Success message to display
        hint: Helper text to display below input
        **kwargs: Additional props to pass to the input
    """
    
    # Get size styles
    current_size = SIZE_VARIANTS["input"].get(size, SIZE_VARIANTS["input"]["large"])
    
    # Build input styles - using minimal styling without custom borders
    input_styles = {
        "width": "100%",
        "padding": current_size["padding"],
        "font_size": current_size["font_size"],
        "font_family": TYPOGRAPHY["font_family"],
        "border": "1px solid #e2e8f0",
        "border_radius": "6px",
        "background": "white",
        "min_height": "40px",
        "box_sizing": "border-box",
    }
    
    # Add error/success styling if needed
    if error:
        input_styles["border_color"] = COLORS["error"]
    elif success:
        input_styles["border_color"] = COLORS["success"]
    
    # Build the input component
    input_component = rx.input(
        placeholder=placeholder,
        name=name,
        value=value,
        on_change=on_change,
        on_blur=on_blur,
        on_focus=on_focus,
        type=input_type,
        required=required,
        disabled=disabled,
        style=input_styles,
        **kwargs
    )
    
    # Build label component if provided
    label_component = None
    if label:
        label_component = rx.el.label(
            label,
            style={
                "font_size": TYPOGRAPHY["font_sizes"]["sm"],
                "font_weight": TYPOGRAPHY["font_weights"]["medium"],
                "color": COLORS["text_secondary"],
                "margin_bottom": "0.25rem",
                "display": "block",
                "font_family": TYPOGRAPHY["font_family"],
            }
        )
    
    # Build message components
    message_components = []
    
    # Error message
    if error and error_message:
        message_components.append(
            rx.el.div(
                error_message,
                style={
                    "font_size": TYPOGRAPHY["font_sizes"]["xs"],
                    "color": COLORS["error"],
                    "margin_top": "0.25rem",
                    "font_family": TYPOGRAPHY["font_family"],
                }
            )
        )
    
    # Success message
    if success and success_message:
        message_components.append(
            rx.el.div(
                success_message,
                style={
                    "font_size": TYPOGRAPHY["font_sizes"]["xs"],
                    "color": COLORS["success"],
                    "margin_top": "0.25rem",
                    "font_family": TYPOGRAPHY["font_family"],
                }
            )
        )
    
    # Hint message
    if hint and not error and not success:
        message_components.append(
            rx.el.div(
                hint,
                style={
                    "font_size": TYPOGRAPHY["font_sizes"]["xs"],
                    "color": COLORS["text_muted"],
                    "margin_top": "0.25rem",
                    "font_family": TYPOGRAPHY["font_family"],
                }
            )
        )
    
    # Build the complete component
    components = []
    if label_component:
        components.append(label_component)
    
    components.append(input_component)
    components.extend(message_components)
    
    return rx.vstack(
        *components,
        width="100%",
        spacing="0",
        align="stretch",
        style={"width": "100%", "gap": "0.25rem"},
    )


def text_input_with_form(
    label: Optional[str] = None,
    placeholder: Optional[str] = None,
    name: Optional[str] = None,
    value: Optional[str] = None,
    on_change: Optional[Callable] = None,
    on_blur: Optional[Callable] = None,
    on_focus: Optional[Callable] = None,
    input_type: str = "text",
    required: bool = False,
    disabled: bool = False,
    size: str = "large",
    variant: str = "default",
    error: bool = False,
    error_message: Optional[str] = None,
    success: bool = False,
    success_message: Optional[str] = None,
    hint: Optional[str] = None,
    server_invalid: bool = False,
    **kwargs
) -> rx.Component:
    """
    Text input wrapped in a form field for better validation integration.
    This version is compatible with Reflex form components.
    """
    
    # Get size styles
    current_size = SIZE_VARIANTS["input"].get(size, SIZE_VARIANTS["input"]["large"])
    
    # Build input styles - using minimal styling without custom borders
    input_styles = {
        "width": "100%",
        "padding": current_size["padding"],
        "font_size": current_size["font_size"],
        "font_family": TYPOGRAPHY["font_family"],
        "border": "1px solid #e2e8f0",
        "border_radius": "6px",
        "background": "white",
        "min_height": "40px",
        "box_sizing": "border-box",
    }
    
    # Add error/success styling if needed
    if error or server_invalid:
        input_styles["border_color"] = COLORS["error"]
    elif success:
        input_styles["border_color"] = COLORS["success"]
    
    # Build the form field
    return rx.form.field(
        rx.flex(
            # Label
            rx.form.label(label) if label else None,
            
            # Input control
            rx.form.control(
                rx.input(
                    placeholder=placeholder,
                    name=name,
                    value=value,
                    on_change=on_change,
                    on_blur=on_blur,
                    on_focus=on_focus,
                    type=input_type,
                    required=required,
                    disabled=disabled,
                    style=input_styles,
                    **kwargs
                ),
                as_child=True,
            ),
            
            # Error message
            rx.cond(
                error and error_message,
                Alert.create(
                    severity="error",
                    title="Error",
                    message=error_message,
                ),
            ),
            
            # Success message
            rx.cond(
                success and success_message,
                rx.form.message(
                    success_message,
                    color=COLORS["success"],
                ),
            ),
            
            # Hint message
            rx.cond(
                hint and not error and not success,
                rx.form.message(
                    hint,
                    color=COLORS["text_muted"],
                ),
            ),
            
            direction="column",
            spacing="0",
            align="stretch",
            style={"width": "100%", "gap": "0.25rem"},
        ),
        name=name,
        server_invalid=server_invalid,
        style={"width": "100%"},
    ) 