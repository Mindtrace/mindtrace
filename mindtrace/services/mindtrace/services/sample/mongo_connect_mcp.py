from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema
from mindtrace.services import Service


class ConnectInput(BaseModel):
    """Connection parameters for MongoDB.

    Provide a standard MongoDB connection URI. Optional fields can override or
    augment URI options (e.g., timeouts).
    """

    uri: str = Field(..., description="MongoDB connection URI, e.g. mongodb://localhost:27017")
    database: Optional[str] = Field(None, description="Optional default database to target after connecting")
    server_selection_timeout_ms: Optional[int] = Field(
        2000, description="Timeout for server selection in milliseconds"
    )


class ConnectOutput(BaseModel):
    """Connection result summary."""

    connected: bool
    message: str
    server_info: Optional[Dict[str, Any]] = None
    databases: Optional[List[str]] = None
    collections: Optional[List[str]] = None


connect_task = TaskSchema(name="connect", input_schema=ConnectInput, output_schema=ConnectOutput)


class MongoConnectService(Service):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Expose as both HTTP endpoint and MCP tool
        self.add_endpoint("connect", self.db_connect, schema=connect_task, as_tool=True)

    def db_connect(self, payload: ConnectInput) -> ConnectOutput:
        """Connect to a MongoDB instance and optionally list databases/collections.

        Inspired by the MongoDB MCP server connect tool. Attempts to establish a
        connection, runs a ping, and returns basic topology details. If a
        database is provided, lists its collections.
        """
        try:
            # Import locally to avoid hard dependency if unused
            from pymongo import MongoClient

            client_kwargs: Dict[str, Any] = {
                "serverSelectionTimeoutMS": payload.server_selection_timeout_ms or 2000,
            }

            client = MongoClient(payload.uri, **client_kwargs)

            # Validate connection
            client.admin.command("ping")

            server_info: Dict[str, Any] = {}
            try:
                # server_info can raise if not available yet; ignore non-critical
                info = client.server_info()
                # Keep only a few safe keys
                for key in ("version", "gitVersion", "maxBsonObjectSize"):  # type: ignore[list-item]
                    if key in info:
                        server_info[key] = info[key]
            except Exception:
                pass

            databases: Optional[List[str]] = None
            collections: Optional[List[str]] = None

            try:
                databases = client.list_database_names()
            except Exception:
                databases = None

            if payload.database:
                try:
                    db = client[payload.database]
                    collections = db.list_collection_names()
                except Exception:
                    collections = None

            return ConnectOutput(
                connected=True,
                message="Successfully connected to MongoDB and executed ping.",
                server_info=server_info or None,
                databases=databases,
                collections=collections,
            )
        except Exception as exc:
            return ConnectOutput(
                connected=False,
                message=f"Connection failed: {exc}",
                server_info=None,
                databases=None,
                collections=None,
            )

