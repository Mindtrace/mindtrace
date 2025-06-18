from reflex_app.backend.database.models.user import User
from reflex_app.backend.core.config import settings
from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
from typing import Optional

backend = MongoMindtraceODMBackend(User, db_uri=settings.MONGO_URI, db_name=settings.DB_NAME)

class UserRepository:
    @staticmethod
    async def get_by_email(email: str) -> Optional[User]:
        await backend.initialize()
        users = await backend.find({"email": email})
        return users[0] if users else None

    @staticmethod
    async def get_by_username(username: str) -> Optional[User]:
        await backend.initialize()
        users = await backend.find({"username": username})
        return users[0] if users else None

    @staticmethod
    async def create_user(user_data: dict) -> User:
        await backend.initialize()
        user = User(**user_data)
        return await backend.insert(user) 