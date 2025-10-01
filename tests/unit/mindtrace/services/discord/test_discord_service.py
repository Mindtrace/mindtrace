"""
Unit tests for the Discord service implementation.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from mindtrace.services.discord.discord_service import DiscordService
from mindtrace.services.discord.types import (
    DiscordCommandInput,
    DiscordCommandOutput,
    DiscordStatusOutput,
    DiscordCommandsOutput
)


class TestDiscordService:
    """Test DiscordService class."""
    
    @pytest.fixture
    def discord_service(self):
        """Create a DiscordService instance for testing."""
        with patch('mindtrace.services.discord.discord_service.DiscordClient') as mock_client:
            mock_client.return_value.bot = Mock()
            mock_client.return_value.bot.user = Mock()
            mock_client.return_value.bot.user.name = "TestBot"
            mock_client.return_value.bot.guilds = []
            mock_client.return_value.bot.users = []
            mock_client.return_value.bot.latency = 0.1
            mock_client.return_value.bot.status = "online"
            mock_client.return_value._commands = {}
            
            service = DiscordService(token="test_token")
            return service
    
    def test_discord_service_initialization(self, discord_service):
        """Test DiscordService initialization."""
        assert discord_service.discord_client is not None
        assert discord_service._bot_task is None
    
    def test_get_bot_status_not_started(self, discord_service):
        """Test bot status when bot is not started."""
        discord_service.discord_client.bot = None
        
        status = discord_service.get_bot_status(None)
        
        assert isinstance(status, DiscordStatusOutput)
        assert status.bot_name is None
        assert status.guild_count == 0
        assert status.user_count == 0
        assert status.latency == 0.0
        assert status.status == "not_started"
    
    def test_get_bot_status_started(self, discord_service):
        """Test bot status when bot is started."""
        status = discord_service.get_bot_status(None)
        
        assert isinstance(status, DiscordStatusOutput)
        assert status.bot_name == "TestBot"
        assert status.guild_count == 0
        assert status.user_count == 0
        assert status.latency == 0.1
        assert status.status == "online"
    
    def test_get_commands(self, discord_service):
        """Test commands endpoint."""
        # Mock commands
        mock_command = Mock()
        mock_command.name = "test"
        mock_command.description = "Test command"
        mock_command.usage = "!test"
        mock_command.aliases = ["t"]
        mock_command.category = "General"
        mock_command.enabled = True
        mock_command.hidden = False
        
        discord_service.discord_client._commands = {"test": mock_command}
        
        commands = discord_service.get_commands(None)
        
        assert isinstance(commands, DiscordCommandsOutput)
        assert len(commands.commands) == 1
        assert commands.commands[0]["name"] == "test"
        assert commands.commands[0]["description"] == "Test command"
    
    @pytest.mark.asyncio
    async def test_execute_command(self, discord_service):
        """Test command execution endpoint."""
        input_data = DiscordCommandInput(
            content="!test",
            author_id=123,
            channel_id=456,
            guild_id=789,
            message_id=101112
        )
        
        output = await discord_service.execute_command(input_data)
        
        assert isinstance(output, DiscordCommandOutput)
        assert "test" in output.response
        assert str(input_data.author_id) in output.response
    
    def test_register_command_delegation(self, discord_service):
        """Test that register_command delegates to discord_client."""
        with patch.object(discord_service.discord_client, 'register_command') as mock_register:
            test_handler = lambda x: None
            discord_service.register_command(
                name="test",
                description="Test command",
                usage="!test",
                handler=test_handler
            )
            
            mock_register.assert_called_once_with(
                name="test",
                description="Test command",
                usage="!test",
                handler=test_handler
            )
    
    def test_register_event_handler_delegation(self, discord_service):
        """Test that register_event_handler delegates to discord_client."""
        with patch.object(discord_service.discord_client, 'register_event_handler') as mock_register:
            mock_handler = Mock()
            discord_service.register_event_handler("MESSAGE", mock_handler)
            
            mock_register.assert_called_once_with("MESSAGE", mock_handler)
    
    @pytest.mark.asyncio
    async def test_startup(self, discord_service):
        """Test service startup."""
        await discord_service.startup()
        
        assert discord_service._bot_task is not None
        assert not discord_service._bot_task.done()  # Task should be running
    
    @pytest.mark.asyncio
    async def test_run_bot(self, discord_service):
        """Test bot running in background task."""
        with patch.object(discord_service.discord_client, 'start_bot', new_callable=AsyncMock) as mock_start:
            await discord_service._run_bot()
            
            mock_start.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_bot_error(self, discord_service):
        """Test bot running with error."""
        with patch.object(discord_service.discord_client, 'start_bot', new_callable=AsyncMock) as mock_start:
            mock_start.side_effect = Exception("Bot error")
            
            with pytest.raises(Exception, match="Bot error"):
                await discord_service._run_bot()
    
    @pytest.mark.asyncio
    async def test_shutdown_cleanup(self, discord_service):
        """Test service shutdown cleanup."""
        # Mock bot task - create a real asyncio.Task that can be awaited
        async def dummy_task():
            pass
        
        mock_task = asyncio.create_task(dummy_task())
        mock_task.cancel = Mock()
        discord_service._bot_task = mock_task
        
        # Mock bot
        with patch.object(discord_service.discord_client, 'stop_bot', new_callable=AsyncMock) as mock_stop:
            await discord_service.shutdown_cleanup()
            
            mock_task.cancel.assert_called_once()
            mock_stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_shutdown_cleanup_no_bot_task(self, discord_service):
        """Test shutdown cleanup when no bot task exists."""
        discord_service._bot_task = None
        
        with patch.object(discord_service.discord_client, 'stop_bot', new_callable=AsyncMock) as mock_stop:
            await discord_service.shutdown_cleanup()
            
            mock_stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_shutdown_cleanup_bot_error(self, discord_service):
        """Test shutdown cleanup with bot stop error."""
        # Mock bot task - create a real asyncio.Task that can be awaited
        async def dummy_task():
            pass
        
        mock_task = asyncio.create_task(dummy_task())
        mock_task.cancel = Mock()
        discord_service._bot_task = mock_task
        
        with patch.object(discord_service.discord_client, 'stop_bot', new_callable=AsyncMock) as mock_stop:
            mock_stop.side_effect = Exception("Stop error")
            
            # Should not raise exception
            await discord_service.shutdown_cleanup()
            
            mock_task.cancel.assert_called_once()
            mock_stop.assert_called_once()
