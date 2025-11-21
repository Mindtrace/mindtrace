import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Generator

from beanie import Indexed
from beanie.odm.fields import PydanticObjectId
from datasets import Features, Image, IterableDataset, List, Sequence, Value
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
    contract: Annotated[str, Indexed(unique=False)] = Field(
        default="default", description="The contract of this datum."
    )
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
    """
    Generator function that converts loaded data to HuggingFace-compatible format.

    This function processes each row of loaded data and transforms it according to
    the contract types specified. For image contracts, it converts paths to strings.
    For other contracts, it passes the data through unchanged.

    Args:
        loaded_data: List of dictionaries, where each dictionary represents a row
            with column names as keys and loaded datum data as values
        contracts: Dictionary mapping column names to their contract types
            (e.g., {"image": "image", "label": "classification"})

    Yields:
        Dictionary for each row with data transformed according to contract types
    """
    for row in loaded_data:
        row_to_yield = {}
        for column, data in row.items():
            if contracts[column] == "image":
                row_to_yield[column] = str(data)
            else:
                row_to_yield[column] = data
        yield row_to_yield


# Mapping from contract types to HuggingFace feature types
# Used when converting datasets to HuggingFace format
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
    updated_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp when the dataset was last updated."
    )
    metadata: dict[str, Any] = Field(
        default_factory=lambda: {}, description="Additional metadata associated with the dataset."
    )
    # datum_ids: dict[str, list[PydanticObjectId]] = Field(default_factory=lambda: defaultdict[str, list[PydanticObjectId]](list), description="Datum IDs of the dataset.")
    datum_ids: list[dict[str, PydanticObjectId]] = Field(default_factory=list, description="Datum IDs of the dataset.")

    async def to_HF(self, datalake: "Datalake") -> IterableDataset:
        """
        Convert the dataset to a HuggingFace IterableDataset.

        This method loads all data from the datalake, determines the appropriate
        HuggingFace feature types based on the contracts, and creates an IterableDataset
        that can be used with HuggingFace's datasets library.

        Args:
            datalake: The Datalake instance to use for loading data

        Returns:
            A HuggingFace IterableDataset with properly typed features

        Raises:
            KeyError: If a contract type is not found in contracts_to_hf_type mapping
            Exception: If data loading fails
        """
        loaded_data = await self.load(datalake)
        features_dict = {column: contracts_to_hf_type[contract] for column, contract in self.contracts.items()}
        hf_type = Features(features_dict)

        return IterableDataset.from_generator(
            gen, gen_kwargs={"loaded_data": loaded_data, "contracts": self.contracts}, features=hf_type
        )

    async def load_row(self, datalake: "Datalake", row: dict[str, PydanticObjectId]) -> dict[str, Any]:
        loaded_row = {}
        # Load all datum IDs for this row, preserving the mapping to columns
        # Create a list of tuples (column, datum_id) to preserve order
        column_id_pairs = list(row.items())
        datum_ids = [datum_id for _, datum_id in column_id_pairs]
        datums = await datalake.get_data(datum_ids)
        if not self.contracts:
            for (column, _), datum in zip(column_id_pairs, datums):
                self.contracts[column] = datum.contract
        else:
            for (column, _), datum in zip(column_id_pairs, datums):
                if self.contracts[column] != datum.contract:
                    raise ValueError(
                        f"All datums in a column must have the same contract, but datum id {datum.id} in column {column} has contract {datum.contract} when the column contract is {self.contracts[column]}"
                    )
        # Map the loaded data back to their column names
        for (column, _), datum in zip(column_id_pairs, datums):
            loaded_row[column] = datum.data
        return loaded_row

    async def load(self, datalake: "Datalake") -> list[dict[str, Any]]:
        """
        Load all data for this dataset from the datalake.

        This method retrieves the actual data for all datum IDs in the dataset,
        validates that all datums in each column have the same contract, and
        returns the loaded data in the same row-oriented format as datum_ids.

        The contracts are automatically detected from the first row and stored
        in self.contracts. All subsequent rows are validated to ensure consistency.

        Args:
            datalake: The Datalake instance to use for loading data

        Returns:
            List of dictionaries, where each dictionary represents a row with
            column names as keys and loaded datum data as values.
            Example: [{"image": path1, "label": {"label": "cat", "confidence": 0.95}}, ...]

        Raises:
            ValueError: If datums in the same column have different contracts
            Exception: If data retrieval from the datalake fails
        """
        return await asyncio.gather(*[self.load_row(datalake, row) for row in self.datum_ids])
