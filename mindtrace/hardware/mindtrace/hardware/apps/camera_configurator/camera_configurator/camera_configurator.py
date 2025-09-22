"""Main Camera Configurator Reflex application.

A standalone camera configuration and management interface for hardware control.
Provides real-time camera discovery, initialization, configuration, and image capture.
"""

import reflex as rx
from .pages.index import index_page
from .pages.camera_config import camera_config_page
from .styles.theme import theme_config

# Create the main Reflex app
app = rx.App(
    theme=theme_config,
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap"
    ],
    style={
        "font_family": "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif",
        "margin": "0",
        "padding": "0",
        "*": {
            "box_sizing": "border-box",
        },
        "body": {
            "margin": "0",
            "padding": "0",
            "width": "100vw",
            "height": "100vh",
            "overflow_x": "auto",
            "background": "linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 50%, #f8fafc 100%)",
        },
        "html": {
            "margin": "0", 
            "padding": "0",
            "width": "100%",
            "height": "100%",
        },
        "#root": {
            "width": "100vw",
            "min_height": "100vh",
            "margin": "0",
            "padding": "0",
        }
    },
)

# Add routes
app.add_page(
    index_page,
    route="/",
    title="Camera Configurator - Home",
    description="Camera hardware configuration and management interface",
)

app.add_page(
    camera_config_page,
    route="/config",
    title="Camera Configurator - Advanced Configuration",
    description="Advanced camera parameter configuration",
)