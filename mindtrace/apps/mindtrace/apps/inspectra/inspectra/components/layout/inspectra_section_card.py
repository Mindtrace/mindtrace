import reflex as rx

from inspectra.styles.global_styles import DS


def inspectra_section_card(title: str, content: rx.Component) -> rx.Component:
    """Generic wrapper for chart or table sections."""
    return rx.box(
        rx.text(title, color=DS.color.text_primary, font_weight=DS.text.weight_medium),
        rx.box(
            content,
            background_color=DS.color.surface,
            border_radius=DS.radius.md,
            padding=DS.space_px.md,
            box_shadow="0 1px 3px rgba(0,0,0,0.05)",
        ),
        margin_bottom=DS.space_px.lg,
    )
