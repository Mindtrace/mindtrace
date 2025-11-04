import reflex as rx
from inspectra.state.auth_state import AuthState

def index() -> rx.Component:
    return rx.vstack(
        rx.heading("Inspectra Dashboard", size="6"),
        rx.text("Welcome to your global operations overview."),
        rx.text("Plant performance, line metrics, and alerts are displayed here."),
        spacing="4",
        align="start",
    )
