import reflex as rx

from poseidon.styles.global_styles import THEME as T


def main_css_animation() -> rx.Component:
    """
    CSS animations and keyframes for mindtrace components.
    """
    return rx.html(
        f"""
        <style>
            {T.animations.float}
            {T.animations.shimmer}
            {T.animations.fadeInUp}
            {T.animations.slideInUp}
            {T.animations.fadeIn}
            {T.animations.shake}
            

            

            
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
