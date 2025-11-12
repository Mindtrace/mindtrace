import reflex as rx

from inspectra.styles.global_styles import DS


def inspectra_data_table(columns: list[str], rows: list[list[str]]) -> rx.Component:
    """Token-driven generic table."""
    return rx.table_container(
        rx.table(
            rx.thead(rx.tr(*[rx.th(c, color=DS.color.text_secondary) for c in columns])),
            rx.tbody(*[rx.tr(*[rx.td(v) for v in row]) for row in rows]),
        ),
        border=f"1px solid {DS.color.border}",
        border_radius=DS.radius.md,
        background_color=DS.color.surface,
        box_shadow="0 1px 3px rgba(0,0,0,0.05)",
    )
