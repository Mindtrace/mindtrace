from typing import List, Type, TypeVar

from beanie import Document, PydanticObjectId, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from mindtrace.database.backends.mindtrace_odm_backend import MindtraceODMBackend
from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError


class MindtraceDocument(Document):
    """
    Base document class for MongoDB collections in Mindtrace.

    This class extends Beanie's Document class to provide a standardized
    base for all MongoDB document models in the Mindtrace ecosystem.

    Example:
        .. code-block:: python

            from mindtrace.database.backends.mongo_odm_backend import MindtraceDocument

            class User(MindtraceDocument):
                name: str
                email: str

                class Settings:
                    name = "users"
                    use_cache = True
    """

    class Settings:
        """
        Configuration settings for the document.

        Attributes:
            use_cache (bool): Whether to enable caching for this document type.
        """

        use_cache = False


ModelType = TypeVar("ModelType", bound=MindtraceDocument)


class MongoMindtraceODMBackend[T: MindtraceDocument](MindtraceODMBackend):
    """
    MongoDB implementation of the Mindtrace ODM backend.

    This backend provides asynchronous database operations using MongoDB as the
    underlying storage engine. It uses Beanie ODM for document modeling and
    Motor for async MongoDB operations.

    Args:
        model_cls (Type[ModelType]): The document model class to use for operations.
        db_uri (str): MongoDB connection URI string.
        db_name (str): Name of the MongoDB database to use.

    Example:
        .. code-block:: python

            from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend

            class User(MindtraceDocument):
                name: str
                email: str

            backend = MongoMindtraceODMBackend(
                model_cls=User,
                db_uri="mongodb://localhost:27017",
                db_name="mindtrace_db"
            )

            # Initialize and use
            await backend.initialize()
            user = await backend.insert(User(name="John", email="john@example.com"))
    """

    def __init__(self, model_cls: Type[T], db_uri: str, db_name: str):
        """
        Initialize the MongoDB ODM backend.

        Args:
            model_cls (Type[ModelType]): The document model class to use for operations.
            db_uri (str): MongoDB connection URI string.
            db_name (str): Name of the MongoDB database to use.
        """
        super().__init__()
        self.model_cls: Type[T] = model_cls
        self.client = AsyncIOMotorClient(db_uri)
        self.db_name = db_name
        self._is_initialized = False

    async def initialize(self):
        """
        Initialize the MongoDB connection and document models.

        This method sets up the Beanie ODM with the specified database and
        registers the document models. It should be called before performing
        any database operations.

        Example:
            .. code-block:: python

                backend = MongoMindtraceODMBackend(User, "mongodb://localhost:27017", "mydb")
                await backend.initialize()
        """
        if not self._is_initialized:
            await init_beanie(database=self.client[self.db_name], document_models=[self.model_cls])
            self._is_initialized = True

    def is_async(self) -> bool:
        """
        Determine if this backend operates asynchronously.

        Returns:
            bool: Always returns True as MongoDB operations are asynchronous.

        Example:
            .. code-block:: python

                backend = MongoMindtraceODMBackend(User, "mongodb://localhost:27017", "mydb")
                if backend.is_async():
                    result = await backend.insert(user)
        """
        return True

    async def insert(self, obj: BaseModel) -> T:
        """
        Insert a new document into the MongoDB collection.

        Args:
            obj (BaseModel): The document object to insert into the database.

        Returns:
            ModelType: The inserted document with generated fields populated.

        Raises:
            DuplicateInsertError: If the document violates unique constraints.

        Example:
            .. code-block:: python

                user = User(name="John", email="john@example.com")
                try:
                    inserted_user = await backend.insert(user)
                    print(f"Inserted user with ID: {inserted_user.id}")
                except DuplicateInsertError as e:
                    print(f"Duplicate entry: {e}")
        """
        await self.initialize()
        doc = self.model_cls(**obj.model_dump())
        try:
            return await doc.insert()
        except DuplicateKeyError as e:
            raise DuplicateInsertError(f"Duplicate key error: {str(e)}")
        except Exception as e:
            raise DuplicateInsertError(str(e))

    async def get(self, id: str | PydanticObjectId) -> T:
        """
        Retrieve a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to retrieve.

        Returns:
            ModelType: The retrieved document.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.

        Example:
            .. code-block:: python

                try:
                    user = await backend.get("507f1f77bcf86cd799439011")
                    print(f"Found user: {user.name}")
                except DocumentNotFoundError:
                    print("User not found")
        """
        await self.initialize()
        doc = await self.model_cls.get(id)
        if not doc:
            raise DocumentNotFoundError(f"Object with id {id} not found")
        return doc

    async def delete(self, id: str):
        """
        Delete a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to delete.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.

        Example:
            .. code-block:: python

                try:
                    await backend.delete("507f1f77bcf86cd799439011")
                    print("User deleted successfully")
                except DocumentNotFoundError:
                    print("User not found")
        """
        await self.initialize()
        doc = await self.model_cls.get(id)
        if doc:
            await doc.delete()
        else:
            raise DocumentNotFoundError(f"Object with id {id} not found")

    async def all(self) -> List[T]:
        """
        Retrieve all documents from the collection.

        Returns:
            List[ModelType]: A list of all documents in the collection.

        Example:
            .. code-block:: python

                all_users = await backend.all()
                print(f"Found {len(all_users)} users")
                for user in all_users:
                    print(f"- {user.name}")
        """
        await self.initialize()
        return await self.model_cls.find_all().to_list()

    async def find(self, *args, **kwargs) -> List[T]:
        """
        Find documents matching the specified criteria.

        Args:
            *args: Query conditions and filters.
            **kwargs: Additional query parameters.

        Returns:
            List[ModelType]: A list of documents matching the query criteria.

        Example:
            .. code-block:: python

                # Find users with specific email
                users = await backend.find(User.email == "john@example.com")

                # Find users with name containing "John"
                users = await backend.find({"name": {"$regex": "John"}})
        """
        await self.initialize()
        return await self.model_cls.find(*args, **kwargs).to_list()

    async def aggregate(self, pipeline: list) -> List[T]:
        """
        Execute a MongoDB aggregation pipeline.

        Args:
            pipeline (list): The aggregation pipeline stages.

        Returns:
            list: The aggregation results.

        Example:
            .. code-block:: python

                # Group users by age and count
                pipeline = [
                    {"$group": {"_id": "$age", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}}
                ]
                results = await backend.aggregate(pipeline)
        """
        await self.initialize()
        return await self.model_cls.get_motor_collection().aggregate(pipeline).to_list(None)

    def get_raw_model(self) -> Type[T]:
        """
        Get the raw document model class used by this backend.

        Returns:
            Type[ModelType]: The document model class.

        Example:
            .. code-block:: python

                model_class = backend.get_raw_model()
                print(f"Using model: {model_class.__name__}")
        """
        return self.model_cls
