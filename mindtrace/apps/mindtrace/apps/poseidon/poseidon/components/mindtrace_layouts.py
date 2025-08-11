"""Mindtrace Layout Components - Background, Page Layout, and CSS Animations."""

import reflex as rx
from poseidon.styles.global_styles import COLORS, SIZING, ANIMATIONS


def background_mindtrace() -> rx.Component:
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


def page_layout_mindtrace(children, **kwargs) -> rx.Component:
    """
    Main page layout with background and container.
    """
    return rx.box(
        background_mindtrace(),
        rx.container(
            rx.box(
                *children,
                width="100%",
                padding=SIZING["container_padding"],
            ),
            center_content=True,
            style={
                "min_height": "100vh",
                "display": "flex",
                "align_items": "center",
                "justify_content": "center",
                "padding": "1.5rem 0",
            }
        ),
        style={
            "min_height": "100vh",
            "background": COLORS["background_primary"],
            "width": "100%",
            "position": "relative",
        },
        **kwargs
    )


def css_animations_mindtrace() -> rx.Component:
    """
    CSS animations and keyframes for mindtrace components.
    """
    return rx.html(
        f"""
        <style>
            {ANIMATIONS["float"]}
            {ANIMATIONS["shimmer"]}
            {ANIMATIONS["fadeInUp"]}
            {ANIMATIONS["slideInUp"]}
            {ANIMATIONS["fadeIn"]}
            {ANIMATIONS["shake"]}
            

            
            /* Global button styling */
            button {{
                font-weight: 600 !important;
                font-family: "Inter", system-ui, sans-serif !important;
                border-radius: 12px !important;
                background: linear-gradient(135deg, #0057FF 0%, #0041CC 100%) !important;
                color: white !important;
                border: none !important;
                cursor: pointer !important;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
                box-shadow: 0 4px 16px rgba(0, 87, 255, 0.3) !important;
            }}
            
            /* Button size variants */
            button[data-size="small"] {{
                padding: 0.5rem 1rem !important;
                font-size: 0.875rem !important;
            }}
            
            button[data-size="medium"] {{
                padding: 0.75rem 1.5rem !important;
                font-size: 0.925rem !important;
            }}
            
            button[data-size="large"], button:not([data-size]) {{
                padding: 1rem 2rem !important;
                font-size: 1rem !important;
            }}
            
            button:hover {{
                transform: translateY(-2px) !important;
                box-shadow: 0 8px 24px rgba(0, 87, 255, 0.4) !important;
                background: linear-gradient(135deg, #0041CC 0%, #003399 100%) !important;
            }}
            
            /* Global select styling */
            select {{
                border-radius: 12px !important;
                background: rgba(248, 250, 252, 0.8) !important;
                border: 2px solid rgba(226, 232, 240, 0.6) !important;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
                color: rgb(51, 65, 85) !important;
                font-family: "Inter", system-ui, sans-serif !important;
                backdrop-filter: blur(10px) !important;
                outline: none !important;
                cursor: pointer !important;
            }}
            
            /* Select size variants */
            select[data-size="small"] {{
                padding: 0.5rem 0.75rem !important;
                font-size: 0.875rem !important;
            }}
            
            select[data-size="medium"] {{
                padding: 0.75rem 1rem !important;
                font-size: 0.925rem !important;
            }}
            
            select[data-size="large"], select:not([data-size]) {{
                padding: 1rem 1.25rem !important;
                font-size: 0.95rem !important;
            }}
            
            select:focus {{
                border-color: #0057FF !important;
                background: rgba(255, 255, 255, 0.95) !important;
                box-shadow: 0 0 0 4px rgba(0, 87, 255, 0.1), 0 4px 12px rgba(0, 87, 255, 0.15) !important;
                transform: translateY(-1px) !important;
            }}
            
            select:hover {{
                border-color: rgba(0, 87, 255, 0.3) !important;
                background: rgba(255, 255, 255, 0.9) !important;
            }}
        </style>
        """
    ) 