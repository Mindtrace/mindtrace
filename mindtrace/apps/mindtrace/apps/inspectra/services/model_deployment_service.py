"""
Model deployment service.

Deploys a model for a line. Currently mocked to return fixed deployment details.
Replace with real deployment logic when integrating with the actual model server.
"""

from typing import Any, Dict

MOCK_MODEL_SERVER_URL = "http://192.168.50.31:8001"


async def deploy_model_for_line(model_id: str, model_name: str, version: str) -> Dict[str, Any]:
    """Deploy a model for a line. Returns deployment details on success.

    Currently mocked: always returns a dict with model_server_url and deployment_status.
    """
    _ = model_id, model_name, version
    return {"model_server_url": MOCK_MODEL_SERVER_URL, "deployment_status": "active"}


async def take_down_model_deployment(deployment_id: str) -> None:
    """Take down a model deployment.

    Currently mocked: no-op.
    """
    _ = deployment_id

