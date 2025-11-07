import asyncio

from inspectra.backend.db.init import init_db
from inspectra.backend.db.repos.line import LineRepo
from inspectra.backend.db.repos.organization import OrganizationRepo
from inspectra.backend.db.repos.plant import PlantRepo
from inspectra.backend.db.repos.user import UserAlreadyExistsError, UserRepo
from inspectra.backend.services.user_service import UserService


async def seed_demo_user() -> None:
    await init_db()

    org = await OrganizationRepo.get_or_create("Demo Org")
    plant = await PlantRepo.get_or_create("Demo Plant", org_id=org.id)
    line = await LineRepo.get_or_create("Demo Line", plant_id=plant.id)

    try:
        user = await UserService.register(
            email="demo@mail.com",
            password="123456",
            name="Demo User",
        )
    except UserAlreadyExistsError:
        user = await UserRepo.get_by_email("demo@mail.com")
        if not user:
            raise

    await UserRepo.assign_scope(
        user.id,
        org_ids=[org.id],
        plant_ids=[plant.id],
        line_ids=[line.id],
    )


if __name__ == "__main__":
    asyncio.run(seed_demo_user())
