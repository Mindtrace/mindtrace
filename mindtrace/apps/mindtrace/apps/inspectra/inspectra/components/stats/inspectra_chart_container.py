import reflex as rx
from inspectra.styles.global_styles import DS

def inspectra_chart_container(title: str, chart: rx.Component) -> rx.Component:
    """Standard wrapper for charts."""
    return rx.box(
        rx.text(title, color=DS.color.text_primary, font_weight=DS.text.weight_medium),
        chart,
        background_color=DS.color.surface,
        border_radius=DS.radius.md,
        padding=DS.space_px.md,
        box_shadow="0 1px 3px rgba(0,0,0,0.05)",
    )
