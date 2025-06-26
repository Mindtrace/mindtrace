import reflex as rx

class PoseidonConfig(rx.Config):
    pass

config = PoseidonConfig(
    app_name="poseidon",
    db_url="sqlite:///poseidon.db",
    env=rx.Env.DEV,
) 