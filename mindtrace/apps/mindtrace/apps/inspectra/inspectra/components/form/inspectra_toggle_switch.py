import reflex as rx
from inspectra.styles.global_styles import DS

def inspectra_toggle_switch(label: str, value: bool = True) -> rx.Component:
    """Token-styled switch."""
    return rx.hstack(
        rx.text(label, color=DS.color.text_primary, font_size=DS.text.size_sm),
        rx.switch(is_checked=value),
        spacing=DS.space_token.sm,
    )
