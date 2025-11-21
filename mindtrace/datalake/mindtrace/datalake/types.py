from beanie.odm.fields import PydanticObjectId


from datetime import datetime
from typing import Annotated, Any, TYPE_CHECKING, Generator
from PIL import Image as PILImage
from beanie import Indexed, PydanticObjectId
from datasets import Image, IterableDataset, Value, List, Features, Sequence
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
    contract: str = Field(default="default", description="The contract of this datum.")
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

def gen(loaded_data: list[dict[str, Any]], contracts: dict[str, str]) -> Generator[dict[str, Any], None, None]:
    for row in loaded_data:
        row_to_yield = {}
        for column, data in row.items():
            if contracts[column] == "image":
                row_to_yield[column] = str(data)
            else:
                row_to_yield[column] = data
        yield row_to_yield


contracts_to_hf_type = {
    "image": Image(),
    "classification": {"label": Value("string"), "confidence": Value("float")},
    "bbox": {"bbox": List(Sequence(Value("float"), length=4))},
}

class Dataset(MindtraceDocument):
    """
    A dataset in the datalake system.
    """
    name: str = Field(description="Name of the dataset.")
    description: str = Field(description="Description of the dataset.")
    contracts: dict[str, str] = Field(default_factory=dict, description="Contracts of the dataset.")
    created_at: datetime = Field(default_factory=datetime.now, description="Timestamp when the dataset was created.")
    updated_at: datetime = Field(default_factory=datetime.now, description="Timestamp when the dataset was last updated.")
    metadata: dict[str, Any] = Field(default_factory=lambda: {}, description="Additional metadata associated with the dataset.")
    # datum_ids: dict[str, list[PydanticObjectId]] = Field(default_factory=lambda: defaultdict[str, list[PydanticObjectId]](list), description="Datum IDs of the dataset.")
    datum_ids: list[dict[str, PydanticObjectId]] = Field(default_factory=list, description="Datum IDs of the dataset.")

    async def to_HF(self, datalake: "Datalake") -> IterableDataset:
        loaded_data = await self.load(datalake)
        features_dict = {
            column: contracts_to_hf_type[contract] for column, contract in self.contracts.items()
        }
        hf_type = Features(features_dict)

        return IterableDataset.from_generator(gen, gen_kwargs={"loaded_data": loaded_data, "contracts": self.contracts}, features=hf_type)

    async def load(self, datalake: "Datalake"):
        # Return a list of dicts in the same format as datum_ids, but with loaded data
        # datum_ids: [{"image": id1, "label": label1}, {"image": id2, "label": label2}]
        # Returns: [{"image": data1, "label": data1}, {"image": data2, "label": data2}]
        loaded_rows = []
        contracts = {}
        for i, row in enumerate(self.datum_ids):
            loaded_row = {}
            # Load all datum IDs for this row, preserving the mapping to columns
            # Create a list of tuples (column, datum_id) to preserve order
            column_id_pairs = list(row.items())
            datum_ids = [datum_id for _, datum_id in column_id_pairs]
            datums = await datalake.get_data(datum_ids)
            if i == 0:
                for (column, _), datum in zip(column_id_pairs, datums):
                    contracts[column] = datum.contract
            else:
                for (column, _), datum in zip(column_id_pairs, datums):
                    if contracts[column] != datum.contract:
                        raise ValueError(f"All datums in a column must have the same contract, but entry {i} column {column} has contract {datum.contract} when the column contract is {contracts[column]}")
            # Map the loaded data back to their column names
            for (column, _), datum in zip(column_id_pairs, datums):
                loaded_row[column] = datum.data
            loaded_rows.append(loaded_row)
        self.contracts = contracts
        return loaded_rows