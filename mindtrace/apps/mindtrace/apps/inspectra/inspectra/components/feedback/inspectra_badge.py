import reflex as rx

from inspectra.styles.global_styles import DS


def inspectra_badge(text: str, background: str | None = None) -> rx.Component:
    """Minimal badge component."""
    return rx.box(
        rx.text(text, color=DS.color.surface, font_size=DS.text.size_sm, font_weight=DS.text.weight_medium),
        background_color=background or DS.color.brand,
        padding=f"0 {DS.space_px.sm}",
        border_radius=DS.radius.sm,
    )
