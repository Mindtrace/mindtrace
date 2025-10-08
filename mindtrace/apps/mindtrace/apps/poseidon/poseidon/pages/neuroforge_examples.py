import reflex as rx

def neuroforge_examples() -> rx.Component:
    return rx.box(
        rx.text("NeuroForge - Examples", font_size="2xl", font_weight="bold"),
        padding="2rem",
        min_height="100vh",
        display="flex",
        align_items="center",
        justify_content="center",
    )