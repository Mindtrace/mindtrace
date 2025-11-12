import reflex as rx
from inspectra.styles.global_styles import DS

def inspectra_toast(message: str, background: str | None = None) -> rx.Component:
    """Toast notification – parent sets color."""
    return rx.box(
        rx.text(message, color=DS.color.surface, font_size=DS.text.size_sm),
        background_color=background or DS.color.brand_light,
        padding=f"{DS.space_px.sm} {DS.space_px.md}",
        border_radius=DS.radius.md,
        box_shadow="0 2px 6px rgba(0,0,0,0.15)",
        position="fixed",
        bottom=DS.space_px.lg,
        right=DS.space_px.lg,
        z_index=DS.z.overlay,
    )
