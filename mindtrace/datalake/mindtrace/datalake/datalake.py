import asyncio
import copy
import random
from collections import defaultdict
from typing import Any, Dict, Literal, Optional, overload
from uuid import uuid4

from beanie import PydanticObjectId

from mindtrace.core import Mindtrace
from mindtrace.database import MongoMindtraceODMBackend
from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.types import Datum
from mindtrace.registry import Registry
from mindtrace.registry.backends.local_registry_backend import LocalRegistryBackend


class Datalake(Mindtrace):
    """
    A data lake implementation that manages both database-stored and registry-stored data.

    The Datalake class provides a unified interface for storing and retrieving data
    that can be persisted either directly in a MongoDB database or in external
    registry backends.

    Attributes:
        mongo_db_name: Name of the MongoDB database to use
        mongo_db_uri: URI connection string for MongoDB
        datum_database: Backend for storing DatabaseSavedDatum objects
        registries: Cache of registry instances keyed by URI
    """

    def __init__(self, mongo_db_uri: str, mongo_db_name: str) -> None:
        """
        Initialize the Datalake with MongoDB connection parameters.

        Args:
            mongo_db_uri: MongoDB connection URI
            mongo_db_name: Name of the MongoDB database to use

        Raises:
            Exception: If database initialization fails
        """
        self.mongo_db_name: str = mongo_db_name
        self.mongo_db_uri: str = mongo_db_uri
        self.datum_database: MongoMindtraceODMBackend[Datum] = MongoMindtraceODMBackend(
            model_cls=Datum,
            db_name=self.mongo_db_name,
            db_uri=self.mongo_db_uri,
        )
        self.registries: Dict[str, Registry] = {}

    async def initialize(self):
        await self.datum_database.initialize()

    @classmethod
    async def create(cls, mongo_db_uri: str, mongo_db_name: str) -> "Datalake":
        """
        Create a Datalake instance from a configuration dictionary.
        """
        datalake = cls(mongo_db_uri=mongo_db_uri, mongo_db_name=mongo_db_name)
        await datalake.initialize()
        return datalake

    async def add_datum(
        self,
        data: Any,
        metadata: Dict[str, Any],
        registry_uri: Optional[str] = None,
        derived_from: Optional[PydanticObjectId] = None,
    ) -> Datum:
        """
        Add a datum to the datalake asynchronously.

        Args:
            data: The data to store
            metadata: Metadata associated with the datum
            registry_uri: Optional registry URI for external storage
            derived_from: Optional ID of the parent datum

        Returns:
            The created datum with assigned ID
        """
        if registry_uri:
            # Store in registry
            uuid = str(uuid4())
            if registry_uri not in self.registries:
                self.registries[registry_uri] = Registry(backend=LocalRegistryBackend(uri=registry_uri))
            self.registries[registry_uri].save(uuid, data, metadata=metadata)
            datum = Datum(
                data=None,
                registry_uri=registry_uri,
                registry_key=uuid,
                derived_from=derived_from,
                metadata=metadata,
            )
        else:
            # Store in database
            datum = Datum(
                data=data,
                registry_uri=None,
                registry_key=None,
                derived_from=derived_from,
                metadata=metadata,
            )
        inserted_datum = await self.datum_database.insert(datum)
        return inserted_datum

    async def get_datum(self, datum_id: PydanticObjectId | None) -> Datum:
        """
        Retrieve a datum by its ID.

        This method searches for the datum in both the database-stored and
        registry-stored collections. For registry-stored data, it automatically
        loads the actual data from the registry backend and populates the
        datum.data field.

        Args:
            datum_id: The unique identifier of the datum to retrieve

        Returns:
            The datum if found, None otherwise. For registry-stored data,
            the datum.data field will be populated with the actual data
            loaded from the registry.

        Raises:
            DocumentNotFoundError: If the datum is not found
            Exception: If registry operations fail during data loading
        """
        if datum_id is None:
            raise DocumentNotFoundError("Datum ID is None")
        datum = await self.datum_database.get(datum_id)
        if datum.registry_uri is None:
            return datum
        if datum.registry_uri not in self.registries:
            self.registries[datum.registry_uri] = Registry(backend=LocalRegistryBackend(uri=datum.registry_uri))
        assert datum.registry_key is not None
        data = self.registries[datum.registry_uri].load(datum.registry_key)
        datum.data = data
        return datum

    async def get_data(self, datum_ids: list[PydanticObjectId]) -> list[Datum]:
        """
        Retrieve multiple data by their IDs.

        Args:
            datum_ids: List of unique identifiers of the data to retrieve

        Returns:
            List of data. Each entry will be a Datum instance if found, None otherwise.
            For registry-stored data, the datum.data field will be populated with
            the actual data loaded from the registry.

        Raises:
            Exception: If registry operations fail during data loading
        """
        return await asyncio.gather(*[self.get_datum(datum_id) for datum_id in datum_ids])

    async def get_directly_derived_data(self, datum_id: PydanticObjectId) -> list[PydanticObjectId]:
        """
        Get the IDs of all data that were directly derived from the specified datum.

        Args:
            datum_id: The unique identifier of the parent datum

        Returns:
            List of IDs of data that were directly derived from the specified datum

        Raises:
            Exception: If database query fails
        """
        entries = await self.datum_database.find({"derived_from": datum_id})
        return [entry.id for entry in entries if entry.id is not None]

    async def get_indirectly_derived_data(self, datum_id: PydanticObjectId) -> list[PydanticObjectId]:
        """
        Get the IDs of all data that were indirectly derived from the specified datum.

        This method performs a breadth-first search to find all descendants of the
        specified datum, including data derived from data that were derived from
        the original datum, and so on.

        Args:
            datum_id: The unique identifier of the root datum

        Returns:
            List of IDs of all data in the derivation chain starting from the
            specified datum. Includes the original datum ID and all its descendants.

        Raises:
            Exception: If database queries fail during the traversal
        """
        visited: set[PydanticObjectId] = set()
        queue: list[PydanticObjectId] = [datum_id]
        result: list[PydanticObjectId] = []

        while queue:
            current_id = queue.pop(0)
            if current_id not in visited:
                visited.add(current_id)
                result.append(current_id)
                # Get directly derived data and add to queue
                direct_children = await self.get_directly_derived_data(current_id)
                for child_id in direct_children:
                    if child_id not in visited and child_id not in queue:
                        queue.append(child_id)

        return result

    @overload
    async def query_data(
        self, query: list[dict[str, Any]] | dict[str, Any], datums_wanted: int | None = None, transpose: bool = False
    ) -> list[dict[str, Any]]: ...
    @overload
    async def query_data(
        self,
        query: list[dict[str, Any]] | dict[str, Any],
        datums_wanted: int | None = None,
        transpose: Literal[True] = True,
    ) -> dict[str, list]: ...

    async def query_data(
        self, query: list[dict[str, Any]] | dict[str, Any], datums_wanted: int | None = None, transpose: bool = False
    ) -> list[dict[str, Any]] | dict[str, list]:
        """
        Query the data in the datalake using a list of queries.

        Args:
            query: A list of queries or a single query.
                If a list of queries is provided, the first query is the base query,
                and then the remaining queries are used to obtain derived data.
                So the base query might find images from a certain project, and then
                a second query might find classification labels for those images.
                If no classification label is found for an image, the image id is not included in the result.
                The "derived_from" key indicates the index of the query which creates the data from which this datum should be derived.

                The "strategy" key indicates the strategy to use to determine which datum to use if multiple are found.
                - "latest": The data/datum with the latest added_at timestamp
                - "earliest": The data/datum with the earliest added_at timestamp
                - "random": Randomly selected data/datum
                - "quickest": The first data/datum we find (so "quickest" to run)
                For these three strategies, if no data is found, the entire row (including the base datum) is not included in the result.
                - "missing": if any data is found, the entire row (including the base datum) is not included in the result.
                  This allows us to search for "images we haven't classified yet", for instance.
                  This is not available for the base query.
                If no strategy is provided, "latest" is used.

                Otherwise, the queries have the same syntax as MongoDB filters: https://www.mongodb.com/docs/languages/python/pymongo-driver/current/crud/query/specify-query/

            If a single query is provided, it is used to find the base data and no derived data is obtained.

            datums_wanted: The number of datums to return for each query. If None, all datums are returned.

            transpose: whether to return a list of dictionaries (default, False) or a dictionary of lists (True).

        Returns:
            If transpose is False:
                A list of dictionaries, where each dictionary contains the data of the base datum and the data of
                any derived data, with the number of entries of each dictionary equalling the length of query (minus any entries with the "missing" strategy)
            If transpose is True:
                A dictionary of lists, where the keys are the columns and the values are the lists of values.
        """
        if isinstance(query, dict):
            query = [query]

        assert len(query) > 0
        base_query = copy.deepcopy(query[0])
        base_strategy = base_query.pop("strategy", "latest")
        if base_strategy == "missing":
            raise ValueError("Invalid strategy: missing")
        base_column = base_query.pop("column", None)
        if base_column is None:
            raise ValueError("column must be provided")
        entries = await self.datum_database.find(base_query)
        if datums_wanted is not None:
            assert datums_wanted > 0, "datums_wanted must be greater than 0"
            if base_strategy == "latest":
                entries = sorted(entries, key=lambda x: x.added_at, reverse=True)
            elif base_strategy == "earliest":
                entries = sorted(entries, key=lambda x: x.added_at)
            elif base_strategy == "random":
                random.shuffle(entries)
            elif base_strategy == "quickest":
                pass
            else:
                raise ValueError(f"Invalid strategy: {base_strategy}")  # pragma: no cover

        result_dict = defaultdict(list)
        result_list = []
        for entry in entries:
            this_entry = {base_column: entry.id}
            for subquery in query[1:]:
                subquery = copy.deepcopy(subquery)
                strategy = subquery.pop("strategy", "latest")
                column = subquery.pop("column", None)
                if column is None:
                    raise ValueError("column must be provided")
                if "derived_from" in subquery:
                    subquery["derived_from"] = this_entry[subquery["derived_from"]]

                subquery_entries = await self.datum_database.find(subquery)
                if strategy == "missing":
                    if subquery_entries:
                        break
                else:
                    if not subquery_entries:
                        break
                if strategy == "latest":
                    this_entry[column] = max(subquery_entries, key=lambda x: x.added_at).id
                elif strategy == "earliest":
                    this_entry[column] = min(subquery_entries, key=lambda x: x.added_at).id
                elif strategy == "random":
                    this_entry[column] = random.choice(subquery_entries).id
                elif strategy == "quickest":
                    this_entry[column] = subquery_entries[0].id
                elif strategy == "missing":
                    pass
                else:
                    raise ValueError(f"Invalid strategy: {strategy}")
            else:
                for key, value in this_entry.items():
                    result_dict[key].append(value)
                result_list.append(this_entry)
            if datums_wanted is not None and len(result_list) >= datums_wanted:
                break
        if transpose:
            return result_dict
        else:
            return result_list
