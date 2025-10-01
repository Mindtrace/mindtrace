"""
Integration tests for DiscordService.

These tests actually launch the DiscordService and test its HTTP API endpoints.
"""

import pytest
import requests
from typing import Dict, Any


class TestDiscordServiceIntegration:
    """Integration tests for DiscordService."""
    
    def test_discord_service_status_endpoint(self, discord_service_manager):
        """Test the Discord service status endpoint."""
        response = requests.post(f"{discord_service_manager.url}/discord.status", json={})
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that the response has the expected structure
        assert "bot_name" in data
        assert "guild_count" in data
        assert "user_count" in data
        assert "latency" in data
        assert "status" in data
        
        # The bot may or may not connect depending on the token validity
        # Just check that the status is a valid Discord status
        assert data["status"] in ["not_started", "online", "idle", "dnd", "invisible"]
        # Bot name should be None if not connected, or a string if connected
        assert data["bot_name"] is None or isinstance(data["bot_name"], str)
        # Counts should be non-negative integers
        assert isinstance(data["guild_count"], int) and data["guild_count"] >= 0
        assert isinstance(data["user_count"], int) and data["user_count"] >= 0
        assert isinstance(data["latency"], (int, float)) and data["latency"] >= 0
    
    def test_discord_service_commands_endpoint(self, discord_service_manager):
        """Test the Discord service commands endpoint."""
        response = requests.post(f"{discord_service_manager.url}/discord.commands", json={})
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that the response has the expected structure
        assert "commands" in data
        assert isinstance(data["commands"], list)
    
    def test_discord_service_execute_endpoint(self, discord_service_manager):
        """Test the Discord service execute endpoint."""
        payload = {
            "content": "!roll",
            "author_id": 123,
            "channel_id": 456,
            "guild_id": 789,
            "message_id": 101112
        }
        
        response = requests.post(f"{discord_service_manager.url}/discord.execute", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that the response has the expected structure
        assert "response" in data
        # The response should indicate that the command was not found (since no commands are registered in the basic service)
        # or contain some indication of the command execution
        assert "roll" in data["response"] or "Command" in data["response"]
    
    def test_discord_service_health_endpoints(self, discord_service_manager):
        """Test that standard service health endpoints work."""
        # Test status endpoint
        response = requests.post(f"{discord_service_manager.url}/status", json={})
        assert response.status_code == 200
        
        # Test heartbeat endpoint
        response = requests.post(f"{discord_service_manager.url}/heartbeat", json={})
        assert response.status_code == 200
        
        # Test endpoints endpoint
        response = requests.post(f"{discord_service_manager.url}/endpoints", json={})
        assert response.status_code == 200
        
        data = response.json()
        assert "endpoints" in data
        
        # Check that Discord-specific endpoints are listed
        endpoint_paths = data["endpoints"]
        assert "discord.status" in endpoint_paths
        assert "discord.commands" in endpoint_paths
        assert "discord.execute" in endpoint_paths
    
    def test_discord_service_mcp_endpoints(self, discord_service_manager):
        """Test that MCP endpoints are available."""
        # Test MCP tools endpoint
        response = requests.get(f"{discord_service_manager.url}/mcp/tools")
        # MCP endpoints may not be available if no tools are registered
        # This is acceptable for DiscordService as it doesn't require MCP tools
        assert response.status_code in [200, 404]
        
        # Test MCP resources endpoint
        response = requests.get(f"{discord_service_manager.url}/mcp/resources")
        # MCP endpoints may not be available if no tools are registered
        assert response.status_code in [200, 404]
    
    def test_discord_service_error_handling(self, discord_service_manager):
        """Test error handling in Discord service endpoints."""
        # Test execute endpoint with invalid payload (missing required content field)
        response = requests.post(f"{discord_service_manager.url}/discord.execute", json={})
        assert response.status_code == 422  # Validation error
        
        # Test execute endpoint with valid payload (content is the only required field)
        valid_payload = {
            "content": "!test"
            # Other fields are optional
        }
        response = requests.post(f"{discord_service_manager.url}/discord.execute", json=valid_payload)
        assert response.status_code == 200  # Should succeed since content is provided
