import reflex as rx

class CameraConfiguratorConfig(rx.Config):
    app_name = "camera_configurator"
    api_url = "http://192.168.50.32:8001"

config = CameraConfiguratorConfig(
    app_name="camera_configurator",
    db_url="sqlite:///camera_configurator.db",
    env=rx.Env.DEV,
    port=3001,  # Use different port to avoid conflicts
)