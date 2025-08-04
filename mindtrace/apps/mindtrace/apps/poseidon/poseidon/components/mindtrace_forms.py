"""Mindtrace Form Components - Inputs, Selects, Buttons, and Links."""

import reflex as rx
from typing import List, Dict, Any


def input_mindtrace(
    placeholder: str, 
    name: str, 
    input_type: str = "text", 
    required: bool = True, 
    size: str = "large",
    **kwargs
) -> rx.Component:
    """
    Animated input field with modern styling.
    Supports size variants: small, medium, large (default)
    """
    # Define size variants
    size_styles = {
        "small": {
            "padding": "0.5rem 0.75rem",
            "font_size": "0.875rem",
        },
        "medium": {
            "padding": "0.65rem 0.9rem",
            "font_size": "0.9rem",
        },
        "large": {
            "padding": "0.75rem 1rem",
            "font_size": "0.925rem",
        }
    }
    
    # Get the size style, default to large if invalid size provided
    current_size = size_styles.get(size, size_styles["large"])
    
    return rx.el.input(
        placeholder=placeholder,
        name=name,
        type=input_type,
        required=required,
        style={
            "width": "100%",
            "padding": current_size["padding"],
            "font_size": current_size["font_size"],
            "font_family": '"Inter", system-ui, sans-serif',
            "border_radius": "12px",
            "background": "rgba(248, 250, 252, 0.8)",
            "border": "2px solid rgba(226, 232, 240, 0.6)",
            "outline": "none",
            "transition": "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
            "backdrop_filter": "blur(10px)",
            "color": "rgb(51, 65, 85)",
            "_focus": {
                "border_color": "#0057FF",
                "background": "rgba(255, 255, 255, 0.95)",
                "box_shadow": "0 0 0 4px rgba(0, 87, 255, 0.1), 0 4px 12px rgba(0, 87, 255, 0.15)",
                "transform": "translateY(-1px)",
            },
            "_hover": {
                "border_color": "rgba(0, 87, 255, 0.3)",
                "background": "rgba(255, 255, 255, 0.9)",
            },
            "_placeholder": {
                "color": "rgba(100, 116, 139, 0.6)",
            }
        },
        custom_attrs={"data-size": size},
        **kwargs
    )


def input_with_label_mindtrace(
    label: str, 
    placeholder: str, 
    name: str, 
    input_type: str = "text", 
    required: bool = False,
    size: str = "large"
) -> rx.Component:
    """
    Input field with label using mindtrace styling.
    Supports size variants: small, medium, large (default)
    """
    return rx.vstack(
        rx.el.label(
            label,
            style={
                "font_size": "0.875rem",
                "font_weight": "500",
                "color": "rgb(71, 85, 105)",
                "margin_bottom": "0.5rem",
                "display": "block",
                "font_family": '"Inter", system-ui, sans-serif',
            }
        ),
        input_mindtrace(
            placeholder=placeholder,
            name=name,
            input_type=input_type,
            required=required,
            size=size,
        ),
        width="100%",
        spacing="1",
        style={
            "margin_bottom": "0.5rem",
        }
    )


def input_with_hint_mindtrace(
    label: str, 
    placeholder: str, 
    hint: str, 
    input_type: str = "text", 
    name: str = "", 
    required: bool = False,
    size: str = "large"
) -> rx.Component:
    """
    Input field with label and hint using mindtrace styling.
    Supports size variants: small, medium, large (default)
    """
    return rx.vstack(
        rx.el.label(
            label,
            style={
                "font_size": "0.875rem",
                "font_weight": "500",
                "color": "rgb(71, 85, 105)",
                "margin_bottom": "0.5rem",
                "display": "block",
                "font_family": '"Inter", system-ui, sans-serif',
            }
        ),
        input_mindtrace(
            placeholder=placeholder,
            name=name,
            input_type=input_type,
            required=required,
            size=size,
        ),
        rx.cond(
            hint != "",
            rx.text(
                hint,
                style={
                    "font_size": "0.75rem",
                    "color": "rgb(100, 116, 139)",
                    "margin_top": "0.25rem",
                    "font_family": '"Inter", system-ui, sans-serif',
                }
            ),
        ),
        width="100%",
        spacing="1",
        style={
            "margin_bottom": "0.5rem",
        }
    )


def select_mindtrace(
    label: str, 
    placeholder: str, 
    options: List[Dict[str, Any]], 
    name: str = "", 
    required: bool = False,
    size: str = "large"
) -> rx.Component:
    """
    Modern select field with mindtrace styling.
    Supports size variants: small, medium, large (default)
    """
    # Define size variants
    size_styles = {
        "small": {
            "padding": "0.5rem 0.75rem",
            "font_size": "0.875rem",
        },
        "medium": {
            "padding": "0.65rem 0.9rem",
            "font_size": "0.9rem",
        },
        "large": {
            "padding": "0.75rem 1rem",
            "font_size": "0.925rem",
        }
    }
    
    # Get the size style, default to large if invalid size provided
    current_size = size_styles.get(size, size_styles["large"])
    
    return rx.vstack(
        rx.el.label(
            label,
            style={
                "font_size": "0.875rem",
                "font_weight": "500",
                "color": "rgb(71, 85, 105)",
                "margin_bottom": "0.5rem",
                "display": "block",
                "font_family": '"Inter", system-ui, sans-serif',
            }
        ),
        rx.el.select(
            rx.el.option(placeholder, value="", disabled=True, selected=True),
            rx.foreach(
                options,
                lambda org: rx.el.option(
                    org["name"],
                    value=org["id"]
                )
            ),
            name=name,
            required=required,
            style={
                "width": "100%",
                "padding": current_size["padding"],
                "font_size": current_size["font_size"],
                "font_family": '"Inter", system-ui, sans-serif',
                "border_radius": "12px",
                "background": "rgba(248, 250, 252, 0.8)",
                "border": "2px solid rgba(226, 232, 240, 0.6)",
                "outline": "none",
                "transition": "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                "backdrop_filter": "blur(10px)",
                "color": "rgb(51, 65, 85)",
                "cursor": "pointer",
                "_focus": {
                    "border_color": "#0057FF",
                    "background": "rgba(255, 255, 255, 0.95)",
                    "box_shadow": "0 0 0 4px rgba(0, 87, 255, 0.1)",
                },
                "_hover": {
                    "border_color": "rgba(0, 87, 255, 0.3)",
                    "background": "rgba(255, 255, 255, 0.9)",
                },
            },
            custom_attrs={"data-size": size},
        ),
        width="100%",
        spacing="1",
        style={
            "margin_bottom": "0.5rem",
        }
    )


def button_mindtrace(
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
    # Define color schemes
    color_schemes = {
        "primary": {
            "background": "linear-gradient(135deg, #0057FF 0%, #0041CC 100%)",
            "hover_background": "linear-gradient(135deg, #0041CC 0%, #003399 100%)",
            "shadow": "0 4px 16px rgba(0, 87, 255, 0.3)",
            "hover_shadow": "0 8px 24px rgba(0, 87, 255, 0.4)",
        },
        "danger": {
            "background": "linear-gradient(135deg, #DC2626 0%, #B91C1C 100%)",
            "hover_background": "linear-gradient(135deg, #B91C1C 0%, #991B1B 100%)",
            "shadow": "0 4px 16px rgba(220, 38, 38, 0.3)",
            "hover_shadow": "0 8px 24px rgba(220, 38, 38, 0.4)",
        }
    }
    
    # Define size variants
    size_styles = {
        "small": {
            "padding": "0.5rem 1rem",
            "font_size": "0.875rem",
        },
        "medium": {
            "padding": "0.65rem 1.25rem",
            "font_size": "0.9rem",
        },
        "large": {
            "padding": "0.75rem 1.5rem",
            "font_size": "0.925rem",
        },
    }
    
    scheme = color_schemes.get(variant, color_schemes["primary"])
    current_size = size_styles.get(size, size_styles["large"])
    
    return rx.el.button(
        text,
        type=button_type,
        style={
            "width": "100%",
            "padding": current_size["padding"],
            "font_size": current_size["font_size"],
            "font_weight": "600",
            "font_family": '"Inter", system-ui, sans-serif',
            "border_radius": "12px",
            "background": scheme["background"],
            "color": "white",
            "border": "none",
            "cursor": "pointer",
            "transition": "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
            "box_shadow": scheme["shadow"],
            "position": "relative",
            "overflow": "hidden",
            "outline": "none",
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


def link_mindtrace(text: str, link_text: str, href: str) -> rx.Component:
    """
    Elegant link section with smooth hover animations.
    """
    return rx.box(
        rx.text(
            text,
            display="inline",
            style={
                "color": "rgb(100, 116, 139)",
                "font_size": "0.95rem",
                "font_family": '"Inter", system-ui, sans-serif',
            }
        ),
        rx.link(
            link_text,
            href=href,
            style={
                "color": "#0057FF",
                "font_weight": "500",
                "font_size": "0.95rem",
                "font_family": '"Inter", system-ui, sans-serif',
                "text_decoration": "none",
                "position": "relative",
                "transition": "all 0.3s ease",
                "_hover": {
                    "color": "#0041CC",
                },
                "_after": {
                    "content": "''",
                    "position": "absolute",
                    "bottom": "-2px",
                    "left": "0",
                    "width": "0",
                    "height": "2px",
                    "background": "linear-gradient(90deg, #0057FF, #0041CC)",
                    "transition": "width 0.3s ease",
                },
                "_hover::after": {
                    "width": "100%",
                }
            }
        ),
        text_align="center",
        padding="0.2rem 0",
        style={
            "animation": "fadeIn 0.6s ease-out",
        }
    ) 