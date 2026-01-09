"""Entry point for running Inspectra via `python -m mindtrace.apps.inspectra`."""

from mindtrace.apps.inspectra import InspectraService
from mindtrace.apps.inspectra.core.settings import get_inspectra_config

if __name__ == "__main__":
    config = get_inspectra_config()
    url = config.INSPECTRA.URL

    print(f"Starting Inspectra service at {url}...")
    print("Press Ctrl+C to stop.")

    InspectraService.launch(url=url, block=True)
