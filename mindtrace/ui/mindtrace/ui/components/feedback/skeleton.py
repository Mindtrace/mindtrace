import reflex as rx


def skeleton(
    width: str = "100%",
    height: str = "16px",
    radius: str = "8px",
) -> rx.Component:
    """
    Render a shimmering skeleton placeholder block.

    Commonly used as a loading state for content such as text, cards, or images.

    Args:
        width (str, optional): CSS width of the skeleton block. Defaults to "100%".
        height (str, optional): CSS height of the skeleton block. Defaults to "16px".
        radius (str, optional): CSS border radius for rounded corners. Defaults to "8px".

    Returns:
        rx.Component: A styled Reflex box component with a shimmer animation.
    """
    keyframes = """
    @keyframes mt_shimmer {
      0% { background-position: -200% 0; }
      100% { background-position: 200% 0; }
    }
    """
    return rx.box(
        rx.html(keyframes),
        background="linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 37%, #f1f5f9 63%)",
        background_size="400% 100%",
        animation="mt_shimmer 1.2s infinite",
        border_radius=radius,
        width=width,
        height=height,
    )
