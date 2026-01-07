"""Entry point for running Horizon service via `python -m mindtrace.apps.horizon`.

The service uses the config_overrides pattern - configuration is handled automatically
via HorizonSettings defaults and environment variable overrides (HORIZON__ prefix).

Example:
    # Run with defaults
    python -m mindtrace.apps.horizon

    # Override via environment
    HORIZON__URL=http://0.0.0.0:9000 python -m mindtrace.apps.horizon
"""

from mindtrace.apps.horizon import HorizonService

if __name__ == "__main__":
    print("Starting Horizon service...")
    print("Press Ctrl+C to stop.")

    # Service handles its own configuration via config_overrides pattern
    # URL and other settings come from HorizonSettings defaults + env overrides
    HorizonService.launch(block=True)
