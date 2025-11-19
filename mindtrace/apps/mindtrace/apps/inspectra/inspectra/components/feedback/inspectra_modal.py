import reflex as rx

from inspectra.styles.global_styles import DS


def inspectra_modal(title: str, body: str, confirm_label: str) -> rx.Component:
    """Token-driven modal."""
    return rx.dialog(
        rx.dialog_trigger(rx.button("Open", background_color=DS.color.brand, color=DS.color.surface)),
        rx.dialog_content(
            rx.dialog_header(rx.text(title, color=DS.color.text_primary, font_weight=DS.text.weight_bold)),
            rx.dialog_body(rx.text(body, color=DS.color.text_secondary)),
            rx.dialog_footer(
                rx.button("Cancel", background_color=DS.color.surface, color=DS.color.text_primary),
                rx.button(confirm_label, background_color=DS.color.brand, color=DS.color.surface),
            ),
            background_color=DS.color.surface,
            border_radius=DS.radius.lg,
            padding=DS.space_px.lg,
        ),
    )
