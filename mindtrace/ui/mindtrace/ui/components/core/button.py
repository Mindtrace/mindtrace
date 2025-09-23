import reflex as rx


def button(
    label,
    variant: str = "primary",
    size: str = "md",
    disabled: bool = False,
    on_click=None,
    full_width: bool = False,
):
    """
    Create a styled button component.

    Args:
        label (str): The text displayed on the button.
        variant (str, optional): Visual style of the button. 
            Options: "primary", "secondary", "ghost", "danger", "outline". Defaults to "primary".
        size (str, optional): Button size. 
            Options: "xs", "sm", "md", "lg". Defaults to "md".
        disabled (bool, optional): If True, disables the button. Defaults to False.
        on_click (callable, optional): Function to trigger on button click. Defaults to None.
        full_width (bool, optional): If True, stretches button to full width. Defaults to False.

    Returns:
        rx.Component: A styled Reflex button component.
    """
    sizes = {
        "xs": ("0.25rem 0.5rem", "12px"),
        "sm": ("0.35rem 0.65rem", "12px"),
        "md": ("0.5rem 0.85rem", "14px"),
        "lg": ("0.65rem 1rem", "16px"),
    }
    pad, fs = sizes.get(size, sizes["md"])

    if variant == "primary":
        bg, fg, bd = "#0057FF", "#fff", "none"
        hover_bg = "#0047E0"
    elif variant == "secondary":
        bg, fg, bd = "#fff", "#0f172a", "1px solid #e2e8f0"
        hover_bg = "#fbfdff"
    elif variant == "ghost":
        bg, fg, bd = "transparent", "#0f172a", "none"
        hover_bg = "rgba(0,87,255,.08)"
    elif variant == "danger":
        bg, fg, bd = "#EF4444", "#fff", "none"
        hover_bg = "#DC2626"
    else:  # outline fallback
        bg, fg, bd = "transparent", "#0057FF", "1px solid #0057FF"
        hover_bg = "rgba(0,87,255,.08)"

    return rx.button(
        label,
        on_click=on_click,
        disabled=disabled,
        width="100%" if full_width else "auto",
        padding=pad,
        font_size=fs,
        background=bg,
        color=fg,
        border=bd,
        border_radius="10px",
        transition="all .15s cubic-bezier(.4,0,.2,1)",
        _hover={"background": hover_bg, "transform": "translateY(-1px)"} if not disabled else {},
        _disabled={"opacity": "0.6", "cursor": "not-allowed"},
        cursor="pointer",
    )


def button_group(*children, gap: str = "0.5rem"):
    """
    Create a horizontal group of buttons.

    Args:
        *children: Button components to include in the group.
        gap (str, optional): Space between buttons (CSS value). Defaults to "0.5rem".

    Returns:
        rx.Component: A horizontal stack containing the buttons.
    """
    return rx.hstack(*children, spacing="2", style={"gap": gap})
