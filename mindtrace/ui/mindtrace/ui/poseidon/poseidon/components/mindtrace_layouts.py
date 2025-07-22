"""Mindtrace Layout Components - Background, Page Layout, and CSS Animations."""

import reflex as rx


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
                padding="0 2rem",
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
            "background": "linear-gradient(135deg, #f8fafc 0%, #e2e8f0 50%, #f1f5f9 100%)",
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
        """
        <style>
            @keyframes float {
                0%, 100% { transform: translateY(0px) rotate(0deg); }
                50% { transform: translateY(-15px) rotate(2deg); }
            }
            
            @keyframes shimmer {
                0% { background-position: -200% 0; }
                100% { background-position: 200% 0; }
            }
            
            @keyframes fadeInUp {
                from {
                    opacity: 0;
                    transform: translateY(20px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            @keyframes slideInUp {
                from {
                    opacity: 0;
                    transform: translateY(30px) scale(0.98);
                }
                to {
                    opacity: 1;
                    transform: translateY(0) scale(1);
                }
            }
            
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            
            @keyframes shake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-3px); }
                75% { transform: translateX(3px); }
            }
            
            /* Global input styling */
            input {
                border-radius: 12px;
                background: rgba(248, 250, 252, 0.8);
                border: 2px solid rgba(226, 232, 240, 0.6);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                color: rgb(51, 65, 85);
                font-family: "Inter", system-ui, sans-serif;
                backdrop-filter: blur(10px);
                outline: none;
            }
            
            /* Input size variants */
            input[data-size="small"] {
                padding: 0.5rem 0.75rem;
                font-size: 0.875rem;
            }
            
            input[data-size="medium"] {
                padding: 0.75rem 1rem;
                font-size: 0.925rem;
            }
            
            input[data-size="large"], input:not([data-size]) {
                padding: 1rem 1.25rem;
                font-size: 0.95rem;
            }
            
            input:focus {
                border-color: #0057FF;
                background: rgba(255, 255, 255, 0.95);
                box-shadow: 0 0 0 4px rgba(0, 87, 255, 0.1), 0 4px 12px rgba(0, 87, 255, 0.15);
                transform: translateY(-1px);
            }
            
            input:hover {
                border-color: rgba(0, 87, 255, 0.3);
                background: rgba(255, 255, 255, 0.9);
            }
            
            /* Global button styling */
            button {
                font-weight: 600;
                font-family: "Inter", system-ui, sans-serif;
                border-radius: 12px;
                background: linear-gradient(135deg, #0057FF 0%, #0041CC 100%);
                color: white;
                border: none;
                cursor: pointer;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                box-shadow: 0 4px 16px rgba(0, 87, 255, 0.3);
            }
            
            /* Button size variants */
            button[data-size="small"] {
                padding: 0.5rem 1rem;
                font-size: 0.875rem;
            }
            
            button[data-size="medium"] {
                padding: 0.75rem 1.5rem;
                font-size: 0.925rem;
            }
            
            button[data-size="large"], button:not([data-size]) {
                padding: 1rem 2rem;
                font-size: 1rem;
            }
            
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 24px rgba(0, 87, 255, 0.4);
                background: linear-gradient(135deg, #0041CC 0%, #003399 100%);
            }
            
            /* Global select styling */
            select {
                border-radius: 12px;
                background: rgba(248, 250, 252, 0.8);
                border: 2px solid rgba(226, 232, 240, 0.6);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                color: rgb(51, 65, 85);
                font-family: "Inter", system-ui, sans-serif;
                backdrop-filter: blur(10px);
                outline: none;
                cursor: pointer;
            }
            
            /* Select size variants */
            select[data-size="small"] {
                padding: 0.5rem 0.75rem;
                font-size: 0.875rem;
            }
            
            select[data-size="medium"] {
                padding: 0.75rem 1rem;
                font-size: 0.925rem;
            }
            
            select[data-size="large"], select:not([data-size]) {
                padding: 1rem 1.25rem;
                font-size: 0.95rem;
            }
            
            select:focus {
                border-color: #0057FF;
                background: rgba(255, 255, 255, 0.95);
                box-shadow: 0 0 0 4px rgba(0, 87, 255, 0.1);
            }
            
            select:hover {
                border-color: rgba(0, 87, 255, 0.3);
                background: rgba(255, 255, 255, 0.9);
            }
            
            /* Radix UI Select styling */
            .rt-SelectTrigger {
                color: rgb(51, 65, 85);
                background: rgba(248, 250, 252, 0.8);
                border: 2px solid rgba(226, 232, 240, 0.6);
                border-radius: 12px;
                padding: 1rem 1.25rem;
                font-size: 0.95rem;
                font-family: "Inter", system-ui, sans-serif;
                backdrop-filter: blur(10px);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                min-height: 3rem;
            }
            
            .rt-SelectTrigger:focus {
                border-color: #0057FF;
                background: rgba(255, 255, 255, 0.95);
                box-shadow: 0 0 0 4px rgba(0, 87, 255, 0.1);
            }
            
            .rt-SelectTrigger:hover {
                border-color: rgba(0, 87, 255, 0.3);
                background: rgba(255, 255, 255, 0.9);
            }
            
            .rt-SelectContent {
                background: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(20px);
                border: 1px solid rgba(226, 232, 240, 0.8);
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
                z-index: 1000;
            }
            
            .rt-SelectItem {
                color: rgb(51, 65, 85);
                padding: 0.75rem 1rem;
                transition: all 0.2s ease;
            }
            
            .rt-SelectItem:hover {
                background: rgba(0, 87, 255, 0.08);
                color: #0057FF;
            }
            
            .rt-SelectItem[data-state='checked'] {
                background: rgba(0, 87, 255, 0.12);
                color: #0057FF;
            }
        </style>
        """
    )