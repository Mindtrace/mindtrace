import reflex as rx


def basic_ease_in_background() -> rx.Component:
    """
    Sophisticated animated background with floating elements.
    """
    return rx.box(
        # Floating orbs with animations
        rx.box(
            class_name="floating-orb orb-1",
            position="absolute",
            width="300px",
            height="300px",
            background="radial-gradient(circle, rgba(0, 87, 255, 0.1) 0%, transparent 70%)",
            border_radius="50%",
            top="10%",
            left="10%",
            animation="float 6s ease-in-out infinite",
        ),
        rx.box(
            class_name="floating-orb orb-2",
            position="absolute",
            width="200px",
            height="200px",
            background="radial-gradient(circle, rgba(0, 87, 255, 0.08) 0%, transparent 70%)",
            border_radius="50%",
            top="60%",
            right="15%",
            animation="float 8s ease-in-out infinite reverse",
        ),
        rx.box(
            class_name="floating-orb orb-3",
            position="absolute",
            width="150px",
            height="150px",
            background="radial-gradient(circle, rgba(0, 87, 255, 0.06) 0%, transparent 70%)",
            border_radius="50%",
            bottom="20%",
            left="20%",
            animation="float 7s ease-in-out infinite",
        ),
        position="fixed",
        top="0",
        left="0",
        width="100%",
        height="100%",
        z_index="-1",
        overflow="hidden",
    )
