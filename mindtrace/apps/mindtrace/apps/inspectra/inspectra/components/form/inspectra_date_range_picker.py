import reflex as rx
from inspectra.styles.global_styles import DS

def inspectra_date_range_picker(label: str = "Date Range") -> rx.Component:
    """Date input styled by tokens."""
    return rx.box(
        rx.text(label, color=DS.color.text_secondary, font_size=DS.text.size_sm),
        rx.input(
            type="date",
            border=f"1px solid {DS.color.border}",
            border_radius=DS.radius.sm,
            background_color=DS.color.surface,
            padding=DS.space_px.sm,
        ),
    )
