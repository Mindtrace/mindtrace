import reflex as rx
from inspectra.styles.global_styles import DS

def inspectra_empty_state(message: str = "No data available") -> rx.Component:
    """Neutral empty state block."""
    return rx.center(
        rx.text(message, color=DS.color.text_secondary, font_size=DS.text.size_md),
        height="200px",
        background_color=DS.color.background,
        border=f"1px dashed {DS.color.border}",
        border_radius=DS.radius.md,
    )
