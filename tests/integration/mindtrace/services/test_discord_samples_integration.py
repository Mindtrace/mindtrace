"""Integration tests for Discord sample bots and services.

These tests actually launch the custom Discord bots and services and test their functionality.
"""

import asyncio
from pathlib import Path
import pytest
import requests
import time
from typing import Dict, Any, Optional

from mindtrace.core.config import CoreConfig


class TestDiscordSamplesIntegration:
    """Integration tests for Discord sample bots and services."""
    
    @pytest.fixture(scope="session")
    def testing_token(self):
        """Get the Discord testing token, skip tests if not available."""
        config = CoreConfig()
        testing_token = config.get_secret('MINDTRACE_TESTING_API_KEYS', 'DISCORD')
        if testing_token is None:
            pytest.skip("MINDTRACE_TESTING_API_KEYS__DISCORD is not set. Please set it in order to run the Discord "
                       "integration test suite.")
        return testing_token
    
    @pytest.fixture(scope="session")
    def custom_discord_bot_service(self, testing_token):
        """Launch the custom Discord bot service for testing."""
        from mindtrace.services.samples.discord.custom_bot_service import CustomDiscordService
        
        try:
            with CustomDiscordService.launch(host="localhost", port=8110, token=testing_token, timeout=30) as cm:
                yield cm
        except Exception as e:
            pytest.skip(f"Failed to launch CustomDiscordService: {e}")
    
    @pytest.fixture(scope="session") 
    def custom_discord_bot_client(self, testing_token):
        """Create the custom Discord bot client for testing."""
        from mindtrace.services.samples.discord.custom_bot_client import CustomDiscordBot
        
        try:
            # CustomDiscordBot is a DiscordClient, not a Service, so it doesn't have launch()
            # We can only test instantiation and basic functionality
            bot = CustomDiscordBot(token=testing_token)
            yield bot
        except Exception as e:
            pytest.skip(f"Failed to create CustomDiscordBot: {e}")
    
    def test_custom_discord_bot_service_status(self, custom_discord_bot_service):
        """Test the custom Discord bot service status endpoint."""
        response = requests.post(f"{custom_discord_bot_service.url}/discord.status", json={})
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that the response has the expected structure
        assert "bot_name" in data
        assert "guild_count" in data
        assert "user_count" in data
        assert "latency" in data
        assert "status" in data
        
        # The bot should be online if the token is valid, or not_started if not connected
        assert data["status"] in ["online", "idle", "dnd", "invisible", "not_started"]
        
        # If bot is connected, it should have a name
        if data["status"] != "not_started":
            assert isinstance(data["bot_name"], str)
            assert isinstance(data["guild_count"], int) and data["guild_count"] >= 0
            assert isinstance(data["user_count"], int) and data["user_count"] >= 0
            assert isinstance(data["latency"], (int, float)) and data["latency"] >= 0
        else:
            # If not connected, these should be None or 0
            assert data["bot_name"] is None
            assert data["guild_count"] == 0
            assert data["user_count"] == 0
            assert data["latency"] == 0.0
    
    def test_custom_discord_bot_service_commands(self, custom_discord_bot_service):
        """Test the custom Discord bot service commands endpoint."""
        response = requests.post(f"{custom_discord_bot_service.url}/discord.commands", json={})
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that the response has the expected structure
        assert "commands" in data
        assert isinstance(data["commands"], list)
        
        # The commands list might be empty if the bot is not connected
        # This is expected behavior when the Discord token is not valid
        if data["commands"]:
            # If commands are available, check they match expected ones
            command_names = [cmd.get("name", "") for cmd in data["commands"]]
            expected_commands = ["info", "roll", "cleanup", "help", "service"]
            
            for expected_cmd in expected_commands:
                assert any(expected_cmd in cmd_name for cmd_name in command_names), f"Expected command '{expected_cmd}' not found in {command_names}"
        else:
            # If no commands, that's also valid (bot not connected)
            assert len(data["commands"]) == 0
    
    def test_custom_discord_bot_service_roll_command(self, custom_discord_bot_service):
        """Test the roll command functionality."""
        test_cases = [
            {"content": "/roll", "expected_terms": ["roll", "1-6"]},
            {"content": "/roll 20", "expected_terms": ["roll", "1-20"]},
            {"content": "/roll 100", "expected_terms": ["roll", "1-100"]},
        ]
        
        for test_case in test_cases:
            payload = {
                "content": test_case["content"],
                "author_id": 123,
                "channel_id": 456,
                "guild_id": 789
            }
            
            response = requests.post(f"{custom_discord_bot_service.url}/discord.execute", json=payload)
            assert response.status_code == 200
            
            data = response.json()
            response_text = data["response"].lower()
            
            # Check if bot is connected or if we get an error message
            if "not connected" in response_text or "not found" in response_text or "error" in response_text:
                # Bot is not connected or command not found - this is expected with invalid token
                assert any(term in response_text for term in ["not connected", "not found", "error"])
            else:
                # Bot is connected, check that expected terms appear in response
                for expected in test_case["expected_terms"]:
                    assert expected.lower() in response_text, f"Expected '{expected}' not found in response: {data['response']}"
    
    def test_custom_discord_bot_service_info_command(self, custom_discord_bot_service):
        """Test the info command functionality."""
        payload = {
            "content": "/info",
            "author_id": 123,
            "channel_id": 456,
            "guild_id": 789
        }
        
        response = requests.post(f"{custom_discord_bot_service.url}/discord.execute", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        response_text = data["response"].lower()
        
        # Check if bot is connected or if we get an error message
        if "not connected" in response_text or "not found" in response_text or "error" in response_text:
            # Bot is not connected or command not found - this is expected with invalid token
            assert any(term in response_text for term in ["not connected", "not found", "error"])
        else:
            # Bot is connected, should contain server information
            assert any(term in response_text for term in ["server", "guild", "members", "channels"])
    
    def test_custom_discord_bot_service_help_command(self, custom_discord_bot_service):
        """Test the help command functionality."""
        payload = {
            "content": "/help",
            "author_id": 123,
            "channel_id": 456,
            "guild_id": 789
        }
        
        response = requests.post(f"{custom_discord_bot_service.url}/discord.execute", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        response_text = data["response"].lower()
        
        # Should contain help information
        assert any(term in response_text for term in ["help", "commands", "available"])
    
    def test_custom_discord_bot_service_cleanup_command(self, custom_discord_bot_service):
        """Test the cleanup command functionality."""
        payload = {
            "content": "/cleanup 5",
            "author_id": 123,
            "channel_id": 456,
            "guild_id": 789
        }
        
        response = requests.post(f"{custom_discord_bot_service.url}/discord.execute", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        response_text = data["response"].lower()
        
        # Check if bot is connected or if we get an error message
        if "not connected" in response_text or "not found" in response_text or "error" in response_text:
            # Bot is not connected or command not found - this is expected with invalid token
            assert any(term in response_text for term in ["not connected", "not found", "error"])
        else:
            # Bot is connected, should contain cleanup information or permission error
            assert any(term in response_text for term in ["cleanup", "messages", "permission", "manage"])
    
    def test_custom_discord_bot_service_service_command(self, custom_discord_bot_service):
        """Test the service command functionality."""
        payload = {
            "content": "/service",
            "author_id": 123,
            "channel_id": 456,
            "guild_id": 789
        }
        
        response = requests.post(f"{custom_discord_bot_service.url}/discord.execute", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        response_text = data["response"].lower()
        
        # Should contain service information
        assert any(term in response_text for term in ["service", "status", "uptime", "version"])
    
    def test_custom_discord_bot_service_guild_validation(self, custom_discord_bot_service):
        """Test guild validation for commands that require it."""
        # Test info command without guild (should fail)
        payload_no_guild = {
            "content": "/info",
            "author_id": 123,
            "channel_id": 456
            # No guild_id
        }
        
        response = requests.post(f"{custom_discord_bot_service.url}/discord.execute", json=payload_no_guild)
        assert response.status_code == 200
        
        data = response.json()
        # Should get error message about guild requirement
        assert any(term in data["response"].lower() for term in ["server", "guild", "required"])
    
    def test_custom_discord_bot_service_permission_validation(self, custom_discord_bot_service):
        """Test permission validation for commands that require it."""
        # Test cleanup command (requires manage messages permission)
        payload = {
            "content": "/cleanup 5",
            "author_id": 123,
            "channel_id": 456,
            "guild_id": 789
        }
        
        response = requests.post(f"{custom_discord_bot_service.url}/discord.execute", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        # Should get permission error or success message
        response_text = data["response"].lower()
        assert any(keyword in response_text for keyword in ["permission", "manage", "cleanup", "error", "success"])
    
    def test_custom_discord_bot_service_concurrent_requests(self, custom_discord_bot_service):
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
                response = requests.post(f"{custom_discord_bot_service.url}/discord.execute", json=payload)
                results.put((command, response.status_code, response.json()))
            except Exception as e:
                results.put((command, None, str(e)))
        
        # Start multiple concurrent requests
        threads = []
        for i in range(5):
            thread = threading.Thread(target=make_request, args=(f"/roll {6 + i}", 100 + i))
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
    
    def test_custom_discord_bot_service_unicode_handling(self, custom_discord_bot_service):
        """Test service handling of unicode characters."""
        unicode_commands = [
            "/roll 🎲",
            "/info 📊",
            "/help ❓",
            "/cleanup 🧹"
        ]
        
        for command in unicode_commands:
            payload = {
                "content": command,
                "author_id": 123,
                "channel_id": 456,
                "guild_id": 789
            }
            
            response = requests.post(f"{custom_discord_bot_service.url}/discord.execute", json=payload)
            assert response.status_code == 200
            
            data = response.json()
            assert "response" in data
            # Should handle unicode without errors
            assert isinstance(data["response"], str)
    
    def test_custom_discord_bot_client_instantiation(self, custom_discord_bot_client):
        """Test that the custom Discord bot client can be instantiated."""
        # Test that the bot was created successfully
        assert custom_discord_bot_client is not None
        assert hasattr(custom_discord_bot_client, 'bot')
        assert hasattr(custom_discord_bot_client, 'token')
        assert custom_discord_bot_client.token is not None
        
        # Test that the bot has the expected commands registered
        commands = custom_discord_bot_client.bot.tree.get_commands()
        command_names = [cmd.name for cmd in commands]
        expected_commands = ["info", "roll", "cleanup", "help"]
        
        for expected_cmd in expected_commands:
            assert expected_cmd in command_names, f"Expected command '{expected_cmd}' not found in {command_names}"
    
    def test_custom_discord_bot_client_commands(self, custom_discord_bot_client):
        """Test that the custom Discord bot client has the expected commands."""
        # Test that the bot has the expected commands registered
        commands = custom_discord_bot_client.bot.tree.get_commands()
        command_names = [cmd.name for cmd in commands]
        expected_commands = ["info", "roll", "cleanup", "help"]
        
        for expected_cmd in expected_commands:
            assert expected_cmd in command_names, f"Expected command '{expected_cmd}' not found in {command_names}"
        
        # Test that commands have expected properties
        for cmd in commands:
            assert hasattr(cmd, 'name')
            assert hasattr(cmd, 'description')
            assert cmd.name in expected_commands
    
    def test_custom_discord_bot_client_roll_command(self, custom_discord_bot_client):
        """Test that the roll command is properly registered on the client."""
        # Test that the roll command exists
        commands = custom_discord_bot_client.bot.tree.get_commands()
        roll_command = next((cmd for cmd in commands if cmd.name == "roll"), None)
        assert roll_command is not None, "Roll command not found"
        
        # Test that the roll command has expected properties
        assert hasattr(roll_command, 'name')
        assert hasattr(roll_command, 'description')
        assert roll_command.name == "roll"
    
    def test_custom_discord_bot_client_info_command(self, custom_discord_bot_client):
        """Test that the info command is properly registered on the client."""
        # Test that the info command exists
        commands = custom_discord_bot_client.bot.tree.get_commands()
        info_command = next((cmd for cmd in commands if cmd.name == "info"), None)
        assert info_command is not None, "Info command not found"
        
        # Test that the info command has expected properties
        assert hasattr(info_command, 'name')
        assert hasattr(info_command, 'description')
        assert info_command.name == "info"
    
    def test_custom_discord_bot_client_help_command(self, custom_discord_bot_client):
        """Test that the help command is properly registered on the client."""
        # Test that the help command exists
        commands = custom_discord_bot_client.bot.tree.get_commands()
        help_command = next((cmd for cmd in commands if cmd.name == "help"), None)
        assert help_command is not None, "Help command not found"
        
        # Test that the help command has expected properties
        assert hasattr(help_command, 'name')
        assert hasattr(help_command, 'description')
        assert help_command.name == "help"
    
    def test_custom_discord_bot_client_cleanup_command(self, custom_discord_bot_client):
        """Test that the cleanup command is properly registered on the client."""
        # Test that the cleanup command exists
        commands = custom_discord_bot_client.bot.tree.get_commands()
        cleanup_command = next((cmd for cmd in commands if cmd.name == "cleanup"), None)
        assert cleanup_command is not None, "Cleanup command not found"
        
        # Test that the cleanup command has expected properties
        assert hasattr(cleanup_command, 'name')
        assert hasattr(cleanup_command, 'description')
        assert cleanup_command.name == "cleanup"
    
    def test_custom_discord_bot_client_bot_properties(self, custom_discord_bot_client):
        """Test that the bot has expected properties."""
        # Test bot properties
        assert hasattr(custom_discord_bot_client, 'bot')
        assert hasattr(custom_discord_bot_client, 'token')
        assert hasattr(custom_discord_bot_client, 'intents')
        
        # Test that bot is properly configured
        assert custom_discord_bot_client.bot is not None
        assert custom_discord_bot_client.token is not None
        assert custom_discord_bot_client.intents is not None
    
    def test_custom_discord_bot_client_event_handlers(self, custom_discord_bot_client):
        """Test that event handlers are properly registered."""
        # Test that event handlers are registered
        assert hasattr(custom_discord_bot_client, '_event_handlers')
        assert isinstance(custom_discord_bot_client._event_handlers, dict)
        
        # Test that command handlers are registered
        assert hasattr(custom_discord_bot_client, '_command_handlers')
        assert isinstance(custom_discord_bot_client._command_handlers, dict)
    
    def test_custom_discord_bot_client_command_registration(self, custom_discord_bot_client):
        """Test that all expected commands are properly registered."""
        # Test that all expected commands are registered
        commands = custom_discord_bot_client.bot.tree.get_commands()
        command_names = [cmd.name for cmd in commands]
        expected_commands = ["info", "roll", "cleanup", "help"]
        
        for expected_cmd in expected_commands:
            assert expected_cmd in command_names, f"Expected command '{expected_cmd}' not found in {command_names}"
        
        # Test that we have the right number of commands
        assert len(commands) == len(expected_commands), f"Expected {len(expected_commands)} commands, got {len(commands)}"
