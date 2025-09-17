"""Poseidon Tabs Container Component - Modern Tab Interface."""

import reflex as rx
from typing import List, Dict, Any, Optional

from poseidon.styles.global_styles import C, SP, R, M, Ty, SH, FX

# Tab component variants
TAB_VARIANTS = {
    "root": {
        "width": "100%",
        "font_family": Ty.font_sans,
        "transition": f"all {M.dur} {M.ease}",
    },
    "list": {
        "display": "flex",
        "gap": SP.space_1,
        "transition": f"all {M.dur} {M.ease}",
    },
    "trigger": {
        "font_family": Ty.font_sans,
        "font_size": Ty.fs_base,
        "font_weight": Ty.fw_500,
        "color": C.fg_muted,
        "background": "transparent",
        "border": "none",
        "cursor": "pointer",
        "transition": f"all {M.dur_fast} {M.ease}",
        "outline": "none",
        "position": "relative",
        "white_space": "nowrap",
        # "_hover": {
        #     "color": C.accent,
        #     "background": "rgba(0, 87, 255, 0.05)",
        # },
        "_focus_visible": {
            "outline": "none",
            "box_shadow": f"0 0 0 3px {C.ring}",
        },
        "_data_state_selected": {
            "color": C.accent,
            "font_weight": Ty.fw_600,
        },
    },
    "content": {
        "padding": SP.space_4,
        "outline": "none",
        "animation": "fadeIn 0.3s ease-in-out",
    },
}


def tabs_container(
    tabs: List[Dict[str, Any]],
    default_value: Optional[str] = None,
    orientation: str = "horizontal",
    variant: str = "default",
    **kwargs
) -> rx.Component:
    """
    Ultra-modern tabs container with glass morphism styling.
    
    Args:
        tabs: List of tab dictionaries with 'label', 'value', 'content', and optional 'icon'
        default_value: Default active tab value
        orientation: 'horizontal' or 'vertical'
        variant: 'default', 'pills', 'underline', 'cards'
        **kwargs: Additional props for rx.tabs.root
    """
    
    # Generate tab triggers
    triggers = []
    for tab in tabs:
        trigger_content = []
        
        # Add icon if provided
        if tab.get("icon"):
            trigger_content.append(
                rx.text(tab["icon"], font_size="1.2em", margin_right="0.5em")
            )
        
        # Add label
        trigger_content.append(tab["label"])
        
        triggers.append(
            rx.tabs.trigger(
                rx.hstack(*trigger_content, align_items="center"),
                value=tab["value"],
                disabled=tab.get("disabled", False),
                style=_get_trigger_style(variant, orientation),
            )
        )
    
    # Generate tab contents
    contents = []
    for tab in tabs:
        contents.append(
            rx.tabs.content(
                tab["content"],
                value=tab["value"],
                style=_get_content_style(variant, orientation),
            )
        )
    
    # Determine default value
    if default_value is None and tabs:
        default_value = tabs[0]["value"]
    
    return rx.tabs.root(
        rx.tabs.list(
            *triggers,
            style=_get_list_style(variant, orientation),
        ),
        *contents,
        default_value=default_value,
        orientation=orientation,
        style=_get_root_style(variant, orientation),
        **kwargs,
    )


def _get_root_style(variant: str, orientation: str) -> Dict[str, Any]:
    """Get root container styles based on variant and orientation."""
    base_style = TAB_VARIANTS["root"].copy()
    
    if variant == "cards":
        base_style.update({
            "background": C.surface,
            "border_radius": R.r_xl,
            "border": f"1px solid {C.border}",
            "box_shadow": SH.shadow_2,
            "overflow": "hidden",
        })
    
    return base_style


def _get_list_style(variant: str, orientation: str) -> Dict[str, Any]:
    """Get tab list styles based on variant and orientation."""
    base_style = TAB_VARIANTS["list"].copy()
    
    if orientation == "vertical":
        base_style.update({
            "flex_direction": "column",
            "border_right": f"1px solid {C.border}",
            "padding_right": SP.space_4,
            "margin_right": SP.space_6,
        })
    else:
        base_style.update({
            "flex_direction": "row",
            "border_bottom": f"1px solid {C.border}",
            "padding_bottom": SP.space_2,
            "margin_bottom": SP.space_4,
        })
    
    if variant == "pills":
        base_style.update({
            "background": C.surface_2,
            "border_radius": R.r_full,
            "padding": SP.space_1,
            "border": "none",
        })
    elif variant == "underline":
        base_style.update({
            "border": "none",
            "padding": "0",
        })
    elif variant == "cards":
        base_style.update({
            "background": C.bg,
            "padding": SP.space_4,
            "border": "none",
            "margin": "0",
        })
    
    return base_style


def _get_trigger_style(variant: str, orientation: str) -> Dict[str, Any]:
    """Get tab trigger styles based on variant and orientation."""
    base_style = TAB_VARIANTS["trigger"].copy()
    
    if orientation == "vertical":
        base_style.update({
            "text_align": "left",
            "padding": f"{SP.space_3} {SP.space_4}",
            "border_radius": R.r_md,
            "margin_bottom": SP.space_1,
        })
    else:
        base_style.update({
            "text_align": "center",
            "padding": f"{SP.space_3} {SP.space_4}",
            "border_radius": R.r_md,
        })
    
    if variant == "pills":
        base_style.update({
            "border_radius": R.r_full,
            "padding": f"{SP.space_2} {SP.space_4}",
            "_data_state_selected": {
                "color": C.accent_fg,
                "background": C.accent,
                "box_shadow": SH.shadow_1,
            },
        })
    elif variant == "underline":
        base_style.update({
            "border_radius": "0",
            "padding": f"{SP.space_3} {SP.space_4}",
            "_data_state_selected": {
                "color": C.accent,
                "border_bottom": f"2px solid {C.accent}",
            },
        })
    elif variant == "cards":
        base_style.update({
            "border_radius": R.r_md,
            "padding": f"{SP.space_3} {SP.space_4}",
            "_data_state_selected": {
                "color": C.accent,
                "background": C.surface_2,
                "box_shadow": SH.shadow_1,
            },
        })
    
    return base_style


def _get_content_style(variant: str, orientation: str) -> Dict[str, Any]:
    """Get tab content styles based on variant and orientation."""
    base_style = TAB_VARIANTS["content"].copy()
    
    if variant == "cards":
        base_style.update({
            "background": C.surface,
            "border_radius": R.r_md,
            "margin": SP.space_4,
            "box_shadow": SH.shadow_1,
        })
    
    return base_style


# Convenience functions for common tab configurations
def horizontal_tabs(tabs: List[Dict[str, Any]], **kwargs) -> rx.Component:
    """Create horizontal tabs with default styling."""
    return tabs_container(tabs, orientation="horizontal", **kwargs)


def vertical_tabs(tabs: List[Dict[str, Any]], **kwargs) -> rx.Component:
    """Create vertical tabs with default styling."""
    return tabs_container(tabs, orientation="vertical", **kwargs)


def pill_tabs(tabs: List[Dict[str, Any]], **kwargs) -> rx.Component:
    """Create pill-style tabs."""
    return tabs_container(tabs, variant="pills", **kwargs)


def underline_tabs(tabs: List[Dict[str, Any]], **kwargs) -> rx.Component:
    """Create underline-style tabs."""
    return tabs_container(tabs, variant="underline", **kwargs)


def card_tabs(tabs: List[Dict[str, Any]], **kwargs) -> rx.Component:
    """Create card-style tabs."""
    return tabs_container(tabs, variant="cards", **kwargs) 