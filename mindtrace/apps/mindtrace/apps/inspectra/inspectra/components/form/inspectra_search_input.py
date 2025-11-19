import reflex as rx

from inspectra.styles.global_styles import DS


def inspectra_search_input(placeholder: str = "Search...") -> rx.Component:
    """Neutral search input, token-styled."""
    return rx.input(
        placeholder=placeholder,
        border=f"1px solid {DS.color.border}",
        border_radius=DS.radius.md,
        padding=DS.space_px.sm,
        background_color=DS.color.surface,
        color=DS.color.text_primary,
        width="100%",
    )
