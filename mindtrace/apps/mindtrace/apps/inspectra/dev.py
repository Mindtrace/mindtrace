"""Development entry point for uvicorn with hot reload."""
from mindtrace.apps.inspectra import InspectraService

# Create service instance - uvicorn needs an 'app' variable
_service = InspectraService()
app = _service.app
