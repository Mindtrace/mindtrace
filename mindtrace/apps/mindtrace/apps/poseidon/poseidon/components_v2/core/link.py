"""Core Link Component for Poseidon UI."""

import reflex as rx

from poseidon.styles.global_styles import C, Ty


def link(text: str, link_text: str, href: str) -> rx.Component:
    """
    Elegant link section with smooth hover animations.
    """
    return rx.box(
        rx.text(
            text,
            display="inline",
            style={
                "color": C.fg_muted,
                "font_size": Ty.fs_sm,
                "font_family": Ty.font_sans,
            },
        ),
        rx.link(
            link_text,
            href=href,
            style={
                "color": C.accent,
                "font_weight": Ty.fw_500,
                "font_size": Ty.fs_sm,
                "font_family": Ty.font_sans,
                "text_decoration": "none",
                "position": "relative",
                "transition": "all 0.3s ease",
                "_hover": {
                    "color": C.accent,
                },
                "_after": {
                    "content": "''",
                    "position": "absolute",
                    "bottom": "-2px",
                    "left": "0",
                    "width": "0",
                    "height": "2px",
                    "background": f"linear-gradient(90deg, {C.accent}, {C.ring})",
                    "transition": "width 0.3s ease",
                },
                "_hover::after": {
                    "width": "100%",
                },
            },
        ),
        text_align="center",
        padding="0.2rem 0",
        style={
            "animation": "fadeIn 0.6s ease-out",
        },
    )
