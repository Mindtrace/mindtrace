from fastapi import FastAPI
from mindtrace.apps.inspectra.api.routers import plants, lines, health, auth

app = FastAPI(title="Inspectra Backend", version="0.0.1")

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(plants.router)
app.include_router(lines.router)
