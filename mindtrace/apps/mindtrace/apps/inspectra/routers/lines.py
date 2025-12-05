from fastapi import APIRouter, Depends

from ..core.security import (
    require_user,
    TokenData,
)
from ..schemas.line import LineCreate, LineResponse
from ..services.line_service import LineService

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
