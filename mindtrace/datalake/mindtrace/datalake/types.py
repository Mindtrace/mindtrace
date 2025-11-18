from beanie.odm.fields import PydanticObjectId


from collections import defaultdict
from datetime import datetime
from typing import Annotated, Any, TYPE_CHECKING

from beanie import Indexed, PydanticObjectId
from datasets import Dataset as HuggingFaceDataset, Image
from pydantic import Field

from mindtrace.database import MindtraceDocument
if TYPE_CHECKING:
    from mindtrace.datalake.datalake import Datalake

class Datum(MindtraceDocument):
    """
    A unified data structure for storing both database and registry data.

    The Datum class represents a piece of data in the datalake system that can be stored
    either directly in the database or in an external registry backend. It provides a
    unified interface for managing data regardless of where it's physically stored.

    Attributes:
        data: The actual data content. Can be None if stored in a registry.
        registry_uri: URI of the registry backend where the data is stored (if applicable).
        registry_key: Unique key within the registry for retrieving the data.
        derived_from: ID of the parent datum this datum was derived from.
        metadata: Additional metadata associated with the datum.
    """

    data: Any = Field(default=None, description="The data content of this datum. Can be None if stored in a registry.")
    registry_uri: str | None = Field(
        default=None, description="URI of the registry backend where this datum is stored."
    )
    registry_key: str | None = Field(
        default=None, description="Unique key within the registry for retrieving this datum's data."
    )
    derived_from: Annotated[PydanticObjectId | None, Indexed(unique=False)] = Field(
        default=None, description="ID of the parent datum this datum was derived from."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata associated with this datum."
    )
    added_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp when this datum was added to the datalake."
    )

class Dataset(MindtraceDocument):
    """
    A dataset in the datalake system.
    """
    name: str = Field(description="Name of the dataset.")
    description: str = Field(description="Description of the dataset.")
    created_at: datetime = Field(default_factory=datetime.now, description="Timestamp when the dataset was created.")
    updated_at: datetime = Field(default_factory=datetime.now, description="Timestamp when the dataset was last updated.")
    metadata: dict[str, Any] = Field(default_factory=lambda: {}, description="Additional metadata associated with the dataset.")
    datum_ids: dict[str, list[PydanticObjectId]] = Field(default_factory=lambda: defaultdict[str, list[PydanticObjectId]](list), description="Datum IDs of the dataset.")

    async def to_HF(self, datalake: "Datalake") -> HuggingFaceDataset:
        loaded_data = await self.load(datalake)
        hf_dataset = HuggingFaceDataset.from_dict(loaded_data)
        hf_dataset.cast_column("image", Image(decode=True))
        return hf_dataset

    async def load(self, datalake: "Datalake"):
        loaded_data = {}
        for column, datum_ids in self.datum_ids.items():
            datums = await datalake.get_data(datum_ids)
            loaded_data[column] = [datum.data for datum in datums]
        return loaded_data