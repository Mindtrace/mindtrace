from fastapi import APIRouter, Depends

from ..core.security import (
    require_user,
    TokenData,
)
from ..schemas.plant import PlantCreate, PlantResponse
from ..services.plant_service import PlantService

router = APIRouter(prefix="/plants", tags=["Plants"])

service = PlantService()

@router.get("/", response_model=list[PlantResponse])
async def list_plants(user: TokenData = Depends(require_user)):
    return await service.list_plants()


@router.post("/", response_model=PlantResponse)
async def create_plant(
    payload: PlantCreate,
    user: TokenData = Depends(require_user),
):
    return await service.create_plant(payload)
