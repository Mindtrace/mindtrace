from datetime import datetime
from typing import Annotated, Any

from beanie import Indexed, PydanticObjectId
from pydantic import Field

from mindtrace.database import MindtraceDocument


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
