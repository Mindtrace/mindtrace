import reflex as rx

APP_MODULE = "reflex_app.reflex_app:app"

config = rx.Config(
    app_name="reflex_app",
    db_url="sqlite:///reflex.db",  # or your preferred DB
    env=rx.Env.DEV,  # or rx.Env.PROD for production
) 