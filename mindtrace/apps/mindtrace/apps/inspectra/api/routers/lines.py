from fastapi import APIRouter
from mindtrace.apps.inspectra.api.services.line_service import LineService

router = APIRouter(prefix="/lines", tags=["Lines"])
service = LineService()


@router.get("/")
async def list_lines():
    return await service.list_lines()


@router.post("/")
async def create_line(payload: dict):
    return await service.create_line(payload)
