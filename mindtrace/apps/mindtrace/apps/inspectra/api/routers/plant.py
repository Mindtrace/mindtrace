from fastapi import APIRouter
from mindtrace.apps.inspectra.api.services.plant_service import PlantService

router = APIRouter(prefix="/plants", tags=["Plants"])
service = PlantService()


@router.get("/")
async def list_plants():
    return await service.list_plants()


@router.post("/")
async def create_plant(payload: dict):
    return await service.create_plant(payload)
