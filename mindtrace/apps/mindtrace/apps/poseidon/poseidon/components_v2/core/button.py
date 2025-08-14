"""Dashboard Button Component using Token System"""

from typing import Literal

import reflex as rx

from poseidon.styles.global_styles import THEME as T
from poseidon.styles.variants import COMPONENT_VARIANTS

Variant = Literal[
    "primary",
    "secondary",
    "ghost",
    "danger",
    "link",
    "outline",
]

# Button size variants using tokens
BUTTON_SIZES = {
    "xs": {
        "padding": f"{T.spacing.space_1} {T.spacing.space_3}",
        "font_size": T.typography.fs_xs,
        "height": "1.75rem",
    },
    "sm": {
        "padding": f"{T.spacing.space_2} {T.spacing.space_4}",
        "font_size": T.typography.fs_sm,
        "height": "2rem",
    },
    "md": {
        "padding": f"{T.spacing.space_2} {T.spacing.space_5}",
        "font_size": T.typography.fs_base,
        "height": "2.25rem",
    },
    "lg": {
        "padding": f"{T.spacing.space_3} {T.spacing.space_6}",
        "font_size": T.typography.fs_base,
        "height": "2.50rem",
    },
}


def button(
    text: str = "",
    variant: Variant = "primary",
    size: str = "md",
    icon: str | None = None,
    icon_position: str = "left",
    loading=False,  # may be Var[bool] or bool
    disabled=False,
    full_width=False,
    type: str = "button",
    on_click=None,
    **kwargs,
) -> rx.Component:
    # Extract style from kwargs to merge properly
    additional_styles = kwargs.pop("style", {})

    variant_map = COMPONENT_VARIANTS["button"]
    variant_styles = variant_map.get(variant, variant_map["primary"])
    base_styles = variant_map["base"].copy()
    size_styles = BUTTON_SIZES.get(size, BUTTON_SIZES["md"])

    is_disabled = disabled | loading

    button_styles = {
        **base_styles,
        **variant_styles,
        **size_styles,
        **additional_styles,  # Merge any additional styles
        "width": rx.cond(full_width, "100%", "auto"),
        "opacity": rx.cond(is_disabled, "0.5", "1"),
        "cursor": rx.cond(is_disabled, "not-allowed", "pointer"),
        "pointer_events": rx.cond(is_disabled, "none", "auto"),
    }

    hover_styles = {}
    if variant_styles.get("hover_background"):
        hover_styles["background"] = variant_styles["hover_background"]
    if variant_styles.get("hover_color"):
        hover_styles["color"] = variant_styles["hover_color"]
    if variant_styles.get("hover_border_color"):
        hover_styles["border_color"] = variant_styles["hover_border_color"]
    if variant_styles.get("hover_transform"):
        hover_styles["transform"] = variant_styles["hover_transform"]

    active_styles = {}
    if variant_styles.get("active_transform"):
        active_styles["transform"] = variant_styles["active_transform"]

    content = []

    spinner = rx.box(
        class_name="animate-spin",
        width="1em",
        height="1em",
        style={
            "border": f"2px solid {variant_styles.get('color', T.colors.fg)}",
            "border_top_color": "transparent",
            "border_radius": "50%",
            "animation": "spin 1s linear infinite",
        },
    )
    # show spinner only when loading
    content.append(rx.cond(loading, spinner, rx.fragment()))

    # icons: only gate on python strings; hide if loading via rx.cond
    if icon and icon_position == "left":
        content.append(rx.cond(loading, rx.fragment(), rx.text(icon)))
    if text:
        content.append(rx.text(text))
    if icon and icon_position == "right":
        content.append(rx.cond(loading, rx.fragment(), rx.text(icon)))

    # 6) Event handler guarded by Var

    # 7) Return component
    return rx.button(
        *content,
        type=type,
        on_click=on_click,
        disabled=is_disabled,  # Var-safe
        style=button_styles,  # base/variant/size + reactive props
        _hover=hover_styles,  # pass pseudo styles separately
        _active=active_styles,
        _focus_visible={
            "outline": "none",
            "box_shadow": f"0 0 0 3px {T.colors.ring}",
        },
        **kwargs,
    )


def button_group(*buttons, spacing: str = None, direction: str = "horizontal", **kwargs) -> rx.Component:
    """
    Group multiple buttons together.

    Args:
        *buttons: Button components to group
        spacing: Gap between buttons (uses token spacing)
        direction: horizontal or vertical
        **kwargs: Additional props
    """
    if direction == "vertical":
        return rx.vstack(*buttons, gap=spacing or T.spacing.space_2, **kwargs)
    else:
        return rx.hstack(*buttons, gap=spacing or T.spacing.space_2, **kwargs)
