"""Select Input Component for Poseidon Forms"""

import reflex as rx
from typing import Optional, Callable, Any, List, Dict
from poseidon.styles.global_styles import COLORS, TYPOGRAPHY, SIZE_VARIANTS
from poseidon.styles.variants import COMPONENT_VARIANTS


def select_input(
    label: Optional[str] = None,
    placeholder: Optional[str] = None,
    name: Optional[str] = None,
    value: Optional[str] = None,
    on_change: Optional[Callable] = None,
    items: Optional[List[Dict[str, Any]]] = None,
    required: bool = False,
    disabled: bool = False,
    size: str = "large",
    variant: str = "default",
    error: bool = False,
    error_message: Optional[str] = None,
    success: bool = False,
    success_message: Optional[str] = None,
    hint: Optional[str] = None,
    **kwargs
) -> rx.Component:
    """
    Modern select input component with validation states and error handling.
    
    Args:
        label: Select label text
        placeholder: Placeholder text
        name: Select name attribute
        value: Current selected value
        on_change: Callback for value changes
        items: List of items to display in select
        required: Whether the select is required
        disabled: Whether the select is disabled
        size: Select size variant (small, medium, large)
        variant: Select variant (default, error, success)
        error: Whether to show error state
        error_message: Error message to display
        success: Whether to show success state
        success_message: Success message to display
        hint: Helper text to display below select
        **kwargs: Additional props to pass to the select
    """
    
    # Get size styles
    current_size = SIZE_VARIANTS["input"].get(size, SIZE_VARIANTS["input"]["large"])
    
    # Determine select variant styles
    if error:
        select_variant = "error"
    elif success:
        select_variant = "success"
    elif disabled:
        select_variant = "disabled"
    else:
        select_variant = "base"
    
    # Build select styles
    select_styles = {
        **COMPONENT_VARIANTS["select"]["base"],
        **COMPONENT_VARIANTS["select"][select_variant],
        "padding": current_size["padding"],
        "font_size": current_size["font_size"],
        "background": "white !important",  # Force white background and override global button styles
        "color": COLORS["text_primary"] + " !important",  # Ensure text is readable
        "border": "1px solid #e2e8f0 !important",  # Override global button border
        "box_shadow": "none !important",  # Override global button shadow
        "font_weight": "normal !important",  # Override global button font weight
    }
    
    # Add focus and hover styles if not disabled
    if not disabled:
        select_styles["_focus"] = COMPONENT_VARIANTS["select"]["focus"]
        select_styles["_hover"] = {
            **COMPONENT_VARIANTS["select"]["hover"],
            "background": "white !important",  # Override global button hover background
            "color": COLORS["text_primary"] + " !important",  # Keep text readable on hover
            "border": "1px solid rgba(0, 87, 255, 0.3) !important",  # Subtle blue border on hover
            "box_shadow": "0 0 0 4px rgba(0, 87, 255, 0.1) !important",  # Subtle focus ring
            "font_weight": "normal !important",  # Override global button font weight
        }
    
    # Build the select component using proper Reflex select
    # Use the lower-level components to handle our data format
    select_component = rx.select.root(
        rx.select.trigger(
            placeholder=placeholder,
            style=select_styles,
        ),
        rx.select.content(
            rx.select.group(
                rx.foreach(
                    items,
                    lambda item: rx.select.item(
                        item["name"],
                        value=item["id"]
                    )
                )
            )
        ),
        name=name,
        value=value,
        on_change=on_change,
        required=required,
        disabled=disabled,
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
    
    components.append(select_component)
    components.extend(message_components)
    
    return rx.vstack(
        *components,
        width="100%",
        spacing="0",
        align="stretch",
        style={"width": "100%", "gap": "0.25rem"},
    )


def select_input_with_form(
    label: Optional[str] = None,
    placeholder: Optional[str] = None,
    name: Optional[str] = None,
    value: Optional[str] = None,
    on_change: Optional[Callable] = None,
    items: Optional[List[Dict[str, Any]]] = None,
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
    Select input wrapped in a form field for better validation integration.
    This version is compatible with Reflex form components.
    """
    
    # Get size styles
    current_size = SIZE_VARIANTS["input"].get(size, SIZE_VARIANTS["input"]["large"])
    
    # Determine select variant styles
    if error or server_invalid:
        select_variant = "error"
    elif success:
        select_variant = "success"
    elif disabled:
        select_variant = "disabled"
    else:
        select_variant = "base"
    
    # Build select styles
    select_styles = {
        **COMPONENT_VARIANTS["select"]["base"],
        **COMPONENT_VARIANTS["select"][select_variant],
        "padding": current_size["padding"],
        "font_size": current_size["font_size"],
        "background": "white !important",  # Force white background and override global button styles
        "color": COLORS["text_primary"] + " !important",  # Ensure text is readable
        "border": "1px solid #e2e8f0 !important",  # Override global button border
        "box_shadow": "none !important",  # Override global button shadow
        "font_weight": "normal !important",  # Override global button font weight
    }
    
    # Add focus and hover styles if not disabled
    if not disabled:
        select_styles["_focus"] = COMPONENT_VARIANTS["select"]["focus"]
        select_styles["_hover"] = {
            **COMPONENT_VARIANTS["select"]["hover"],
            "background": "white !important",  # Override global button hover background
            "color": COLORS["text_primary"] + " !important",  # Keep text readable on hover
            "border": "1px solid rgba(0, 87, 255, 0.3) !important",  # Subtle blue border on hover
            "box_shadow": "0 0 0 4px rgba(0, 87, 255, 0.1) !important",  # Subtle focus ring
            "font_weight": "normal !important",  # Override global button font weight
        }
    
    # Build the form field
    return rx.form.field(
        rx.flex(
            # Label
            rx.form.label(label) if label else None,
            
            # Select element using proper Reflex select
            rx.select.root(
                rx.select.trigger(
                    placeholder=placeholder,
                    style=select_styles,
                ),
                rx.select.content(
                    rx.select.group(
                        rx.foreach(
                            items,
                            lambda item: rx.select.item(
                                item["name"],
                                value=item["id"]
                            )
                        )
                    )
                ),
                name=name,
                value=value,
                on_change=on_change,
                required=required,
                disabled=disabled,
                **kwargs
            ),
            
            # Error message
            rx.cond(
                error and error_message,
                rx.form.message(
                    error_message,
                    color=COLORS["error"],
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