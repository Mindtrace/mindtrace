import reflex as rx

from inspectra.styles.global_styles import DS


def inspectra_stat_card(label: str, value: str, subtext: str = "") -> rx.Component:
    """Display a KPI metric card."""
    return rx.box(
        rx.text(label, color=DS.color.text_secondary, font_size=DS.text.size_sm),
        rx.text(value, color=DS.color.text_primary, font_weight=DS.text.weight_bold, font_size=DS.text.size_lg),
        rx.cond(subtext != "", rx.text(subtext, color=DS.color.text_secondary, font_size=DS.text.size_sm)),
        background_color=DS.color.surface,
        border_radius=DS.radius.md,
        padding=DS.space_px.md,
        box_shadow="0 1px 3px rgba(0,0,0,0.05)",
        width="160px",
    )
