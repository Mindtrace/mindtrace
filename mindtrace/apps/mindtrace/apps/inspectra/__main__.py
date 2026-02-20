"""Entry point for running Inspectra via `python -m mindtrace.apps.inspectra`."""

import sys

from mindtrace.apps.inspectra import InspectraService
from mindtrace.apps.inspectra.core.settings import get_inspectra_config
from urllib.parse import urlparse
import uvicorn


def main() -> None:
    """Load config and start Inspectra (uvicorn with --reload in dev, else Service.launch)."""
    config = get_inspectra_config()
    url = config.INSPECTRA.URL

    # Dev mode: run uvicorn with --reload for auto-restart on code changes
    if "--reload" in sys.argv or "-r" in sys.argv:

        parsed = urlparse(url)
        host = parsed.hostname or "0.0.0.0"
        port = parsed.port or 8080
        print(f"Starting Inspectra (dev with reload) at {url}...")
        print("Press Ctrl+C to stop. Code changes will restart the server.")
        uvicorn.run(
            "mindtrace.apps.inspectra.dev:app",
            host=host,
            port=port,
            reload=True,
        )
        return

    print(f"Starting Inspectra service at {url}...")
    print("Press Ctrl+C to stop.")
    InspectraService.launch(url=url, block=True)


if __name__ == "__main__":
    main()
