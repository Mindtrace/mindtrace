"""Entry point for running Horizon service via `python -m mindtrace.apps.horizon`."""

from mindtrace.apps.horizon import HorizonService
from mindtrace.apps.horizon.config import get_horizon_config

if __name__ == "__main__":
    config = get_horizon_config()
    url = config.HORIZON.URL

    print(f"Starting Horizon service at {url}...")
    print("Press Ctrl+C to stop.")

    HorizonService.launch(url=url, block=True)

