"""Core Link Component for Poseidon UI."""

import reflex as rx
from poseidon.styles.global_styles import COLORS, TYPOGRAPHY


def link(text: str, link_text: str, href: str) -> rx.Component:
    """
    Elegant link section with smooth hover animations.
    """
    return rx.box(
        rx.text(
            text,
            display="inline",
            style={
                "color": COLORS["text_secondary"],
                "font_size": "0.95rem",
                "font_family": TYPOGRAPHY["font_family"],
            }
        ),
        rx.link(
            link_text,
            href=href,
            style={
                "color": COLORS["primary"],
                "font_weight": TYPOGRAPHY["font_weights"]["medium"],
                "font_size": "0.95rem",
                "font_family": TYPOGRAPHY["font_family"],
                "text_decoration": "none",
                "position": "relative",
                "transition": "all 0.3s ease",
                "_hover": {
                    "color": COLORS["primary_dark"],
                },
                "_after": {
                    "content": "''",
                    "position": "absolute",
                    "bottom": "-2px",
                    "left": "0",
                    "width": "0",
                    "height": "2px",
                    "background": f"linear-gradient(90deg, {COLORS['primary']}, {COLORS['primary_dark']})",
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