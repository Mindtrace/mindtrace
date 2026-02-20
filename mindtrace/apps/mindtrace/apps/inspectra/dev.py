"""
Dev entry point: exposes the FastAPI app for uvicorn --reload.

Run with auto-reload (code changes restart the server):

  uv run uvicorn mindtrace.apps.inspectra.dev:app --reload --host 0.0.0.0 --port 8080

Or use: uv run python -m mindtrace.apps.inspectra --reload
"""

from mindtrace.apps.inspectra.core.settings import get_inspectra_config
from mindtrace.apps.inspectra.inspectra import InspectraService

_config = get_inspectra_config().INSPECTRA
_service = InspectraService(url=_config.URL)
app = _service.app
