from dataclasses import asdict
from typing import Any, Literal, Type
from uuid import UUID

from fastmcp import FastMCP
from pydantic import BaseModel

from mindtrace.core import named_lambda, TaskSchema
from mindtrace.services import (
    Capability,
    CapabilitiesOutput, 
    CapabilitiesSchema, 
    ExecuteInput,
    ExecuteOutput, 
    ExecuteSchema, 
    IdentityOutput, 
    IdentitySchema,
    SchemaOutput,
    SchemaSchema,
    Service,
    StateOutput,
    StateSchema,
)


class MCPService(Service):
    """Service class extended with MCP-compatible endpoints."""

    def __init__(self, **kwargs):
        self.mcp = FastMCP(name="MCPService")
        super().__init__(**kwargs)
        
        # Register MCP-specific endpoints
        self.add_endpoint("/identity", self.identity, schema=IdentitySchema())
        self.add_endpoint("/capabilities", self.capabilities, schema=CapabilitiesSchema())
        self.add_endpoint("/execute", self.execute, schema=ExecuteSchema())
        self.add_endpoint("/schema", self.schema, schema=SchemaSchema())
        self.add_endpoint("/state", self.state, schema=StateSchema())

    def add_endpoint(self, path, func, *args, **kwargs):
        super().add_endpoint(path, func, *args, **kwargs)
        # Normalize tool name by removing leading slash for MCP
        tool_name = path.lstrip('/')
        self.mcp.tool(name=tool_name)(func)

    def identity(self):
        return IdentityOutput(
            name=self.name,
            version=self.app.version,
            uuid=self.id,
            description=self.app.description,
        )

    def capabilities(self):
        caps = []
        for endpoint, schema in self._endpoints.items():
            if endpoint in {"identity", "capabilities", "execute"}:
                continue
            caps.append(
                Capability(
                    name=endpoint,
                    description=schema.name,
                    input_type=getattr(schema, "input_schema", None).__name__ if getattr(schema, "input_schema", None) else None,
                    output_type=schema.output_schema.__name__ if schema.output_schema else None,
                )
            )
        return CapabilitiesOutput(capabilities=caps)

    def execute(self, data: ExecuteInput):
        pipeline = self._endpoints.get(data.capability)
        if pipeline is None:
            raise fastapi.HTTPException(status_code=404, detail=f"Unknown capability: {data.capability}")
        
        result = pipeline.run(data.inputs or {})
        return ExecuteOutput(output=result)

    def schema(self, t = None):
        return SchemaOutput(schemas={
            name: {
                "input": task.input_schema.model_json_schema() if task.input_schema else None,
                "output": task.output_schema.model_json_schema() if task.output_schema else None,
            }
            for name, task in self._endpoints.items()
            if name not in {"identity", "capabilities", "execute"}
        })

    def state(self, t = None):
        return StateOutput(
            status=self.status.value,
            server_id=str(self.id),
            num_endpoints=len(self._endpoints),
            details={
                "heartbeat": asdict(self.heartbeat()),
            }
        )

    def run_mcp_server(self, host="localhost", port=8080, path="/mcp"):
        """Run the MCP server using FastMCP's HTTP transport"""
        self.mcp.run(transport="http", host=host, port=port, path=path)
