import reflex as rx
import os

class CameraConfiguratorConfig(rx.Config):
    app_name = "camera_configurator"

config = CameraConfiguratorConfig(
    app_name="camera_configurator",
    db_url="sqlite:///camera_configurator.db",
    env=rx.Env.DEV,
    frontend_port=int(os.getenv('CAMERA_UI_FRONTEND_PORT', '3000')),  # Reflex frontend port
    backend_port=int(os.getenv('CAMERA_UI_BACKEND_PORT', '8000')),  # Reflex backend port
)