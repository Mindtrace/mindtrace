import reflex as rx

from inspectra.components.feedback.inspectra_badge import inspectra_badge
from inspectra.styles.global_styles import DS


def inspectra_alert_row(line: str, description: str, severity_color: str, status_color: str) -> rx.Component:
    """Single alert row using external color inputs."""
    return rx.hstack(
        rx.text(line, width="20%", color=DS.color.text_primary),
        rx.text(description, width="40%", color=DS.color.text_secondary),
        inspectra_badge("Severity", severity_color),
        inspectra_badge("Status", status_color),
        justify="space-between",
        padding=f"{DS.space_px.sm} {DS.space_px.md}",
        border_bottom=f"1px solid {DS.color.border}",
    )
