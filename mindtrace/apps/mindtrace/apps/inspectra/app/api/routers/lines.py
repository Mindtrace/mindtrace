from fastapi import APIRouter, Depends

from mindtrace.apps.inspectra.app.api.core.security import (
    require_user,
    TokenData,
)
from mindtrace.apps.inspectra.app.schemas.line import LineCreate, LineResponse
from mindtrace.apps.inspectra.app.services.line_service import LineService

router = APIRouter(prefix="/lines", tags=["Lines"])

service = LineService()

@router.get("/", response_model=list[LineResponse])
async def list_lines(user: TokenData = Depends(require_user)):
    return await service.list_lines()


@router.post("/", response_model=LineResponse)
async def create_line(
    payload: LineCreate,
    user: TokenData = Depends(require_user),
):
    return await service.create_line(payload)
