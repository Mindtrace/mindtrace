from mindtrace.database import Database

class BaseRepository:
    """
    Minimal DB-enabled base repository using mindtrace-database.
    """

    def __init__(self, collection_name: str):
        self.collection = Database().collection(collection_name)

    async def get_all(self):
        return await self.collection.find({})

    async def insert_one(self, data: dict):
        return await self.collection.insert_one(data)

    async def find_by_id(self, id: str):
        return await self.collection.find_one({"_id": id})
