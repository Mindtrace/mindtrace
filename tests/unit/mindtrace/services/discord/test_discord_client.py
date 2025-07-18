"""
Unit tests for the Discord client implementation.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from mindtrace.services.discord.discord_client import (
    BaseDiscordClient,
    DiscordCommand,
    DiscordEventType,
    DiscordEventHandler,
    DiscordCommandInput,
    DiscordCommandOutput,
    DiscordStatusOutput,
    DiscordCommandsOutput
)


class TestDiscordCommand:
    """Test DiscordCommand dataclass."""
    
    def test_discord_command_creation(self):
        """Test creating a DiscordCommand instance."""
        command = DiscordCommand(
            name="test",
            description="Test command",
            usage="!test",
            aliases=["t"],
            category="Test"
        )
        
        assert command.name == "test"
        assert command.description == "Test command"
        assert command.usage == "!test"
        assert command.aliases == ["t"]
        assert command.category == "Test"
        assert command.enabled is True
        assert command.hidden is False


class TestDiscordEventHandler:
    """Test DiscordEventHandler abstract class."""
    
    def test_event_handler_interface(self):
        """Test that DiscordEventHandler is abstract."""
        with pytest.raises(TypeError):
            DiscordEventHandler()


class MockDiscordEventHandler(DiscordEventHandler):
    """Mock event handler for testing."""
    
    def __init__(self):
        self.handled_events = []
    
    async def handle(self, event_type: DiscordEventType, **kwargs):
        """Mock handle method."""
        self.handled_events.append((event_type, kwargs))


class TestBaseDiscordClient:
    """Test BaseDiscordClient class."""
    
    @pytest.fixture
    def mock_bot(self):
        """Create a mock Discord bot."""
        bot = Mock()
        bot.user = Mock()
        bot.user.name = "TestBot"
        bot.guilds = []
        bot.users = []
        bot.latency = 0.1
        bot.status = "online"
        return bot
    
    @pytest.fixture
    def discord_client(self, mock_bot):
        """Create a Discord client instance for testing."""
        with patch('mindtrace.services.discord.discord_client.commands.Bot', return_value=mock_bot):
            client = BaseDiscordClient(
                token="test_token",
                command_prefix="!",
                description="Test bot"
            )
            return client
    
    def test_discord_client_initialization(self, discord_client):
        """Test Discord client initialization."""
        assert discord_client.token == "test_token"
        assert discord_client.command_prefix == "!"
        assert discord_client.bot is not None
        assert isinstance(discord_client._commands, dict)
        assert isinstance(discord_client._event_handlers, dict)
    
    def test_register_command(self, discord_client):
        """Test command registration."""
        async def test_command(ctx, *args):
            return "Test response"
        
        discord_client.register_command(
            name="test",
            description="Test command",
            usage="!test",
            handler=test_command
        )
        
        assert "test" in discord_client._commands
        assert "test" in discord_client._command_handlers
        assert discord_client._commands["test"].name == "test"
        assert discord_client._commands["test"].description == "Test command"
    
    def test_register_event_handler(self, discord_client):
        """Test event handler registration."""
        handler = MockDiscordEventHandler()
        
        discord_client.register_event_handler(DiscordEventType.MESSAGE, handler)
        
        assert DiscordEventType.MESSAGE in discord_client._event_handlers
        assert handler in discord_client._event_handlers[DiscordEventType.MESSAGE]
    
    @pytest.mark.asyncio
    async def test_handle_event(self, discord_client):
        """Test event handling."""
        handler = MockDiscordEventHandler()
        discord_client.register_event_handler(DiscordEventType.MESSAGE, handler)
        
        test_data = {"message": "test"}
        await discord_client._handle_event(DiscordEventType.MESSAGE, **test_data)
        
        assert len(handler.handled_events) == 1
        assert handler.handled_events[0][0] == DiscordEventType.MESSAGE
        assert handler.handled_events[0][1] == test_data
    
    def test_get_bot_status(self, discord_client):
        """Test bot status endpoint."""
        status = discord_client.get_bot_status(None)
        
        assert isinstance(status, DiscordStatusOutput)
        assert status.bot_name == "TestBot"
        assert status.guild_count == 0
        assert status.user_count == 0
        assert status.latency == 0.1
        assert status.status == "online"
    
    def test_get_commands(self, discord_client):
        """Test commands endpoint."""
        # Register a test command first
        async def test_command(ctx, *args):
            return "Test"
        
        discord_client.register_command(
            name="test",
            description="Test command",
            usage="!test",
            handler=test_command
        )
        
        commands = discord_client.get_commands(None)
        
        assert isinstance(commands, DiscordCommandsOutput)
        assert len(commands.commands) == 1
        assert commands.commands[0]["name"] == "test"
    
    @pytest.mark.asyncio
    async def test_execute_command(self, discord_client):
        """Test command execution endpoint."""
        input_data = DiscordCommandInput(
            content="!test",
            author_id=123,
            channel_id=456,
            guild_id=789,
            message_id=101112
        )
        
        output = await discord_client.execute_command(input_data)
        
        assert isinstance(output, DiscordCommandOutput)
        assert "test" in output.response
        assert str(input_data.author_id) in output.response
    
    @pytest.mark.asyncio
    async def test_execute_command_with_permissions(self, discord_client):
        """Test command execution with permission checks."""
        async def admin_command(ctx, *args):
            return "Admin command executed"
        
        discord_client.register_command(
            name="admin",
            description="Admin command",
            usage="!admin",
            handler=admin_command,
            permissions=["administrator"]
        )
        
        # Mock context with no admin permissions
        mock_ctx = Mock()
        mock_ctx.author.guild_permissions.administrator = False
        mock_ctx.send = AsyncMock()
        
        await discord_client._execute_command(mock_ctx, "admin")
        
        # Should send permission error
        mock_ctx.send.assert_called_with("You need the `administrator` permission to use this command.")
    
    @pytest.mark.asyncio
    async def test_execute_disabled_command(self, discord_client):
        """Test executing a disabled command."""
        async def disabled_command(ctx, *args):
            return "This should not execute"
        
        discord_client.register_command(
            name="disabled",
            description="Disabled command",
            usage="!disabled",
            handler=disabled_command,
            enabled=False
        )
        
        mock_ctx = Mock()
        mock_ctx.send = AsyncMock()
        
        await discord_client._execute_command(mock_ctx, "disabled")
        
        # Should send disabled message
        mock_ctx.send.assert_called_with("This command is currently disabled.")
    
    @pytest.mark.asyncio
    async def test_execute_unknown_command(self, discord_client):
        """Test executing an unknown command."""
        mock_ctx = Mock()
        mock_ctx.send = AsyncMock()
        
        await discord_client._execute_command(mock_ctx, "unknown")
        
        # Should send unknown command message
        mock_ctx.send.assert_called_with("Unknown command: unknown")
    
    @pytest.mark.asyncio
    async def test_command_error_handling(self, discord_client):
        """Test command error handling."""
        async def error_command(ctx, *args):
            raise Exception("Test error")
        
        discord_client.register_command(
            name="error",
            description="Error command",
            usage="!error",
            handler=error_command
        )
        
        mock_ctx = Mock()
        mock_ctx.send = AsyncMock()
        
        await discord_client._execute_command(mock_ctx, "error")
        
        # Should send error message
        mock_ctx.send.assert_called_with("An error occurred while executing the command: Test error")


class TestDiscordEventTypes:
    """Test DiscordEventType enum."""
    
    def test_event_types(self):
        """Test that all expected event types exist."""
        expected_types = [
            "message",
            "reaction", 
            "member_join",
            "member_leave",
            "voice_state_update",
            "guild_join",
            "guild_leave"
        ]
        
        for event_type in expected_types:
            # Convert to the actual enum format (MEMBER_JOIN, not MEMBERJOIN)
            enum_name = event_type.upper()
            assert hasattr(DiscordEventType, enum_name)
    
    def test_event_type_values(self):
        """Test event type values."""
        assert DiscordEventType.MESSAGE.value == "message"
        assert DiscordEventType.REACTION.value == "reaction"
        assert DiscordEventType.MEMBER_JOIN.value == "member_join"


class TestDiscordCommandSchemas:
    """Test Discord command input/output schemas."""
    
    def test_discord_command_input(self):
        """Test DiscordCommandInput schema."""
        input_data = DiscordCommandInput(
            content="!test",
            author_id=123,
            channel_id=456,
            guild_id=789,
            message_id=101112
        )
        
        assert input_data.content == "!test"
        assert input_data.author_id == 123
        assert input_data.channel_id == 456
        assert input_data.guild_id == 789
        assert input_data.message_id == 101112
    
    def test_discord_command_output(self):
        """Test DiscordCommandOutput schema."""
        output_data = DiscordCommandOutput(
            response="Test response",
            embed={"title": "Test"},
            delete_after=5.0
        )
        
        assert output_data.response == "Test response"
        assert output_data.embed == {"title": "Test"}
        assert output_data.delete_after == 5.0
    
    def test_discord_command_output_minimal(self):
        """Test DiscordCommandOutput with minimal data."""
        output_data = DiscordCommandOutput(response="Test")
        
        assert output_data.response == "Test"
        assert output_data.embed is None
        assert output_data.delete_after is None 

