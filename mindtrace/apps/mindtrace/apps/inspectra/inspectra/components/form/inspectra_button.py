import reflex as rx
from inspectra.styles.global_styles import DS

def inspectra_button(label: str, background: str | None = None, color: str | None = None) -> rx.Component:
    """Base button, external colors, token defaults."""
    return rx.button(
        rx.text(label),
        background_color=background or DS.color.brand,
        color=color or DS.color.surface,
        border_radius=DS.radius.md,
        padding=f"{DS.space_px.sm} {DS.space_px.md}",
        font_weight=DS.text.weight_medium,
    )
