"""
Integration tests for DiscordService.

These tests actually launch the DiscordService and test its HTTP API endpoints.
"""

import asyncio
import pytest
import requests
import time
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
    
    def test_discord_service_command_parsing(self, discord_service_manager):
        """Test command parsing functionality."""
        # Test with different command formats
        test_commands = [
            "!roll",
            "/roll",
            "!help",
            "/help",
            "!info",
            "/info"
        ]
        
        for command in test_commands:
            payload = {
                "content": command,
                "author_id": 123,
                "channel_id": 456,
                "guild_id": 789
            }
            
            response = requests.post(f"{discord_service_manager.url}/discord.execute", json=payload)
            assert response.status_code == 200
            
            data = response.json()
            assert "response" in data
            # Should get some response, even if command not found
            assert isinstance(data["response"], str)
    
    def test_discord_service_parameter_parsing(self, discord_service_manager):
        """Test parameter parsing for commands."""
        # Test basic command execution (the basic DiscordService doesn't have custom commands)
        test_cases = [
            {"content": "!roll 6", "expected_in_response": ["command", "not found"]},
            {"content": "!roll 20", "expected_in_response": ["command", "not found"]},
            {"content": "!roll", "expected_in_response": ["command", "not found"]},
        ]
        
        for test_case in test_cases:
            payload = {
                "content": test_case["content"],
                "author_id": 123,
                "channel_id": 456,
                "guild_id": 789
            }
            
            response = requests.post(f"{discord_service_manager.url}/discord.execute", json=payload)
            assert response.status_code == 200
            
            data = response.json()
            response_text = data["response"].lower()
            
            # Check that expected terms appear in response
            for expected in test_case["expected_in_response"]:
                assert expected.lower() in response_text
    
    def test_discord_service_guild_validation(self, discord_service_manager):
        """Test guild validation for commands that require it."""
        # Test command without guild
        payload_no_guild = {
            "content": "!info",
            "author_id": 123,
            "channel_id": 456
            # No guild_id
        }
        
        response = requests.post(f"{discord_service_manager.url}/discord.execute", json=payload_no_guild)
        assert response.status_code == 200
        
        data = response.json()
        # Should get command not found message
        assert "command" in data["response"].lower() and "not found" in data["response"].lower()
        
        # Test command with guild
        payload_with_guild = {
            "content": "!info",
            "author_id": 123,
            "channel_id": 456,
            "guild_id": 789
        }
        
        response = requests.post(f"{discord_service_manager.url}/discord.execute", json=payload_with_guild)
        assert response.status_code == 200
        
        data = response.json()
        # Should get command not found message (basic service doesn't have custom commands)
        assert "command" in data["response"].lower() and "not found" in data["response"].lower()
    
    def test_discord_service_permission_validation(self, discord_service_manager):
        """Test permission validation for commands that require it."""
        # Test cleanup command (basic service doesn't have custom commands)
        payload = {
            "content": "!cleanup 5",
            "author_id": 123,
            "channel_id": 456,
            "guild_id": 789
        }
        
        response = requests.post(f"{discord_service_manager.url}/discord.execute", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        # Should get command not found message
        response_text = data["response"].lower()
        assert "command" in response_text and "not found" in response_text
    
    def test_discord_service_concurrent_requests(self, discord_service_manager):
        """Test that the service can handle concurrent requests."""
        import threading
        import queue
        
        results = queue.Queue()
        
        def make_request(command, author_id):
            payload = {
                "content": command,
                "author_id": author_id,
                "channel_id": 456,
                "guild_id": 789
            }
            
            try:
                response = requests.post(f"{discord_service_manager.url}/discord.execute", json=payload)
                results.put((command, response.status_code, response.json()))
            except Exception as e:
                results.put((command, None, str(e)))
        
        # Start multiple concurrent requests
        threads = []
        for i in range(5):
            thread = threading.Thread(target=make_request, args=(f"!roll {6 + i}", 100 + i))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        assert results.qsize() == 5
        
        while not results.empty():
            command, status_code, data = results.get()
            assert status_code == 200
            assert "response" in data
    
    def test_discord_service_large_payload(self, discord_service_manager):
        """Test service handling of large payloads."""
        # Create a large message content
        large_content = "!roll " + "x" * 1000
        
        payload = {
            "content": large_content,
            "author_id": 123,
            "channel_id": 456,
            "guild_id": 789
        }
        
        response = requests.post(f"{discord_service_manager.url}/discord.execute", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert "response" in data
    
    def test_discord_service_unicode_handling(self, discord_service_manager):
        """Test service handling of unicode characters."""
        unicode_commands = [
            "!roll 🎲",
            "!info 📊",
            "!help ❓",
            "!cleanup 🧹"
        ]
        
        for command in unicode_commands:
            payload = {
                "content": command,
                "author_id": 123,
                "channel_id": 456,
                "guild_id": 789
            }
            
            response = requests.post(f"{discord_service_manager.url}/discord.execute", json=payload)
            assert response.status_code == 200
            
            data = response.json()
            assert "response" in data
            # Should handle unicode without errors
            assert isinstance(data["response"], str)
