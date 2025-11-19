import reflex as rx

from inspectra.styles.global_styles import DS


def inspectra_select_dropdown(label: str, options: list[str], value: str = "") -> rx.Component:
    """Dropdown with token-based styling."""
    return rx.box(
        rx.text(label, color=DS.color.text_secondary, font_size=DS.text.size_sm),
        rx.select(
            options,
            default_value=value,
            border=f"1px solid {DS.color.border}",
            padding=DS.space_px.sm,
            border_radius=DS.radius.sm,
            background_color=DS.color.surface,
        ),
    )
