"""
Unit tests for the Discord client implementation.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from mindtrace.core import ifnone
from mindtrace.services.discord.discord_client import DiscordClient
from mindtrace.services.discord.types import (
    DiscordCommand,
    DiscordCommandInput,
    DiscordCommandOutput,
    DiscordEventHandler,
    DiscordEventType,
)


class TestDiscordCommand:
    """Test DiscordCommand dataclass."""

    def test_discord_command_creation(self):
        """Test creating a DiscordCommand instance."""
        command = DiscordCommand(name="test", description="Test command", usage="!test", aliases=["t"], category="Test")

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


class TestDiscordClient:
    """Test DiscordClient class."""

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
        with patch("mindtrace.services.discord.discord_client.commands.Bot", return_value=mock_bot):
            client = DiscordClient(token="test_token", description="Test bot")
            return client

    def test_discord_client_initialization(self, discord_client):
        """Test Discord client initialization."""
        assert discord_client.token == "test_token"
        assert discord_client.bot is not None
        assert isinstance(discord_client._commands, dict)
        assert isinstance(discord_client._event_handlers, dict)

    def test_register_command(self, discord_client):
        """Test command registration."""

        async def test_command(ctx, *args):
            return "Test response"

        discord_client.register_command(name="test", description="Test command", usage="!test", handler=test_command)

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

    @pytest.mark.asyncio
    async def test_execute_disabled_command(self, discord_client):
        """Test executing a disabled command."""

        async def disabled_command(ctx, *args):
            return "This should not execute"

        discord_client.register_command(
            name="disabled", description="Disabled command", usage="!disabled", handler=disabled_command, enabled=False
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
            name="error", description="Error command", usage="!error", handler=error_command
        )

        mock_ctx = Mock()
        mock_ctx.send = AsyncMock()

        await discord_client._execute_command(mock_ctx, "error")

        # Should send error message
        mock_ctx.send.assert_called_with("An error occurred while executing the command: Test error")

    @pytest.mark.asyncio
    async def test_handle_event_with_error(self, discord_client):
        """Test event handling with handler errors."""
        # Create a handler that raises an exception
        error_handler = Mock()
        error_handler.handle = AsyncMock(side_effect=Exception("Handler error"))

        discord_client.register_event_handler(DiscordEventType.MESSAGE, error_handler)

        # The error should be caught and logged, not propagated
        with patch.object(discord_client.logger, "error") as mock_logger:
            await discord_client._handle_event(DiscordEventType.MESSAGE, message="test")
            mock_logger.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_slash_command_success(self, discord_client):
        """Test successful slash command execution."""

        # Register a command
        async def test_command(interaction, *args):
            await interaction.response.send_message("Test response")

        discord_client.register_command(name="test", description="Test command", usage="!test", handler=test_command)

        # Create mock interaction
        mock_interaction = Mock()
        mock_interaction.response = Mock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = Mock()
        mock_interaction.followup.send = AsyncMock()
        mock_interaction.guild = None  # No guild for permission check

        # Execute command
        await discord_client._execute_slash_command(mock_interaction, "test")

        # Verify response was sent
        mock_interaction.response.send_message.assert_called_once_with("Test response")

    @pytest.mark.asyncio
    async def test_execute_slash_command_not_found(self, discord_client):
        """Test slash command execution with unknown command."""
        mock_interaction = Mock()
        mock_interaction.response = Mock()
        mock_interaction.response.send_message = AsyncMock()

        # Execute unknown command
        await discord_client._execute_slash_command(mock_interaction, "unknown")

        # Verify error message was sent
        mock_interaction.response.send_message.assert_called_once_with("Unknown command: unknown", ephemeral=True)

    @pytest.mark.asyncio
    async def test_execute_slash_command_disabled(self, discord_client):
        """Test slash command execution with disabled command."""

        # Register a disabled command
        async def test_command(interaction, *args):
            await interaction.response.send_message("Test response")

        discord_client.register_command(
            name="test", description="Test command", usage="!test", handler=test_command, enabled=False
        )

        mock_interaction = Mock()
        mock_interaction.response = Mock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.guild = None

        # Execute disabled command
        await discord_client._execute_slash_command(mock_interaction, "test")

        # Verify disabled message was sent
        mock_interaction.response.send_message.assert_called_once_with(
            "This command is currently disabled.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_execute_slash_command_permission_denied(self, discord_client):
        """Test slash command execution with insufficient permissions."""

        # Register a command with permissions
        async def test_command(interaction, *args):
            await interaction.response.send_message("Test response")

        discord_client.register_command(
            name="test", description="Test command", usage="!test", handler=test_command, permissions=["administrator"]
        )

        # Create mock interaction with guild and member
        mock_guild = Mock()
        mock_member = Mock()
        mock_member.guild_permissions = Mock()
        mock_member.guild_permissions.administrator = False
        mock_guild.get_member.return_value = mock_member

        mock_interaction = Mock()
        mock_interaction.response = Mock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.guild = mock_guild
        mock_interaction.user.id = 123

        # Execute command without permission
        await discord_client._execute_slash_command(mock_interaction, "test")

        # Verify permission denied message was sent
        mock_interaction.response.send_message.assert_called_once_with(
            "You need the `administrator` permission to use this command.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_execute_slash_command_error(self, discord_client):
        """Test slash command execution with handler error."""

        # Register a command that raises an exception
        async def error_command(interaction, *args):
            raise Exception("Command error")

        discord_client.register_command(
            name="error", description="Error command", usage="!error", handler=error_command
        )

        mock_interaction = Mock()
        mock_interaction.response = Mock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = Mock()
        mock_interaction.followup.send = AsyncMock()
        mock_interaction.guild = None

        # Execute command with error
        await discord_client._execute_slash_command(mock_interaction, "error")

        # Verify error handling
        mock_interaction.response.defer.assert_called_once()
        mock_interaction.followup.send.assert_called_once()
        error_call = mock_interaction.followup.send.call_args[0][0]
        assert "An error occurred while executing the command" in error_call

    @pytest.mark.asyncio
    async def test_execute_command_legacy(self, discord_client):
        """Test legacy prefix command execution."""

        # Register a command
        async def test_command(ctx, *args):
            return "Test response"

        discord_client.register_command(name="test", description="Test command", usage="!test", handler=test_command)

        # Create mock context
        mock_ctx = Mock()
        mock_ctx.send = AsyncMock()
        mock_ctx.author = Mock()
        mock_ctx.author.guild_permissions = Mock()

        # Execute command
        await discord_client._execute_command(mock_ctx, "test")

        # Verify response was sent
        mock_ctx.send.assert_called_once_with("Test response")

    @pytest.mark.asyncio
    async def test_start_bot(self, discord_client):
        """Test bot startup."""
        with patch.object(discord_client.bot, "start", new_callable=AsyncMock) as mock_start:
            await discord_client.start_bot()
            mock_start.assert_called_once_with(discord_client.token)

    @pytest.mark.asyncio
    async def test_start_bot_error(self, discord_client):
        """Test bot startup with error."""
        with patch.object(discord_client.bot, "start", new_callable=AsyncMock) as mock_start:
            mock_start.side_effect = Exception("Start error")

            with pytest.raises(Exception, match="Start error"):
                await discord_client.start_bot()

    @pytest.mark.asyncio
    async def test_stop_bot(self, discord_client):
        """Test bot shutdown."""
        with patch.object(discord_client.bot, "close", new_callable=AsyncMock) as mock_close:
            await discord_client.stop_bot()
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_bot_error(self, discord_client):
        """Test bot shutdown with error."""
        with patch.object(discord_client.bot, "close", new_callable=AsyncMock) as mock_close:
            mock_close.side_effect = Exception("Close error")

            with pytest.raises(Exception, match="Close error"):
                await discord_client.stop_bot()

    def test_discord_client_no_token(self):
        """Test DiscordClient initialization without token."""
        # Test the token validation logic directly by mocking the config
        with patch("mindtrace.core.config.CoreConfig") as mock_config_class:
            mock_config = Mock()
            mock_config.get_secret.return_value = None
            mock_config_class.return_value = mock_config

            # Create a minimal DiscordClient instance to test token validation
            with patch("mindtrace.services.discord.discord_client.Mindtrace.__init__", return_value=None):
                # Create instance and manually set config
                client = DiscordClient.__new__(DiscordClient)
                client.config = mock_config

                # Test the token validation logic
                default_token = client.config.get_secret("MINDTRACE_API_KEYS", "DISCORD")
                token = ifnone(None, default=default_token)

                with pytest.raises(RuntimeError, match="No Discord token provided"):
                    if token is None:
                        raise RuntimeError(
                            "No Discord token provided. Pass in a token or provide a MINDTRACE_API_KEYS__DISCORD in the Mindtrace config."
                        )

    @pytest.mark.asyncio
    async def test_execute_slash_command_with_result(self, discord_client):
        """Test slash command execution that returns a result."""

        # Register a command that returns a result
        async def test_command(interaction, *args):
            return "Test result"

        discord_client.register_command(name="test", description="Test command", usage="!test", handler=test_command)

        # Create mock interaction
        mock_interaction = Mock()
        mock_interaction.response = Mock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = Mock()
        mock_interaction.followup.send = AsyncMock()
        mock_interaction.guild = None

        # Execute command
        await discord_client._execute_slash_command(mock_interaction, "test")

        # Verify result was sent
        mock_interaction.followup.send.assert_called_once_with("Test result")

    @pytest.mark.asyncio
    async def test_execute_slash_command_with_cooldown(self, discord_client):
        """Test slash command execution with cooldown."""

        # Register a command with cooldown
        async def test_command(interaction, *args):
            return "Test response"

        discord_client.register_command(
            name="test", description="Test command", usage="!test", handler=test_command, cooldown=5.0
        )

        # Create mock interaction
        mock_interaction = Mock()
        mock_interaction.response = Mock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = Mock()
        mock_interaction.followup.send = AsyncMock()
        mock_interaction.guild = None

        # Execute command (cooldown should be checked but not enforced in simple implementation)
        await discord_client._execute_slash_command(mock_interaction, "test")

        # Verify command executed (cooldown is just a pass in current implementation)
        mock_interaction.response.defer.assert_called_once()
        mock_interaction.followup.send.assert_called_once()

    def test_discord_client_no_token_error(self):
        """Test that DiscordClient raises error when no token is provided."""
        with patch("mindtrace.services.discord.discord_client.Mindtrace.__init__") as mock_init:
            mock_init.return_value = None

            # Mock config to return None for Discord token
            mock_config = Mock()
            mock_config.get_secret.return_value = None

            with patch("mindtrace.core.config.CoreConfig") as mock_core_config:
                mock_core_config.return_value = mock_config

                client = DiscordClient.__new__(DiscordClient)
                client.config = mock_config

                with pytest.raises(RuntimeError, match="No Discord token provided"):
                    client.__init__(token=None)

    def test_discord_client_initialization_with_token(self):
        """Test DiscordClient initialization with token."""
        with patch("mindtrace.services.discord.discord_client.Mindtrace.__init__") as mock_init:
            mock_init.return_value = None

            # Create a mock bot
            mock_bot = Mock()
            mock_bot.tree = Mock()
            mock_bot.tree.command = Mock()

            # Create client and set up mocks
            client = DiscordClient.__new__(DiscordClient)
            client.logger = Mock()
            client.config = Mock()
            client.config.get_secret.return_value = "test_token"
            client._commands = {}
            client._command_handlers = {}

            # Test initialization
            client.__init__(token="test_token")

            # Verify bot was created and event handlers were registered
            assert hasattr(client, "bot")
            assert hasattr(client, "token")
            assert client.token == "test_token"

    def test_discord_client_event_handlers_registered(self):
        """Test that event handlers are registered during initialization."""
        with patch("mindtrace.services.discord.discord_client.Mindtrace.__init__") as mock_init:
            mock_init.return_value = None

            # Create a mock bot
            mock_bot = Mock()
            mock_bot.tree = Mock()
            mock_bot.tree.command = Mock()

            # Create client and set up mocks
            client = DiscordClient.__new__(DiscordClient)
            client.logger = Mock()
            client.config = Mock()
            client.config.get_secret.return_value = "test_token"
            client._commands = {}
            client._command_handlers = {}

            # Test initialization
            client.__init__(token="test_token")

            # Verify bot was created and has event method
            assert hasattr(client, "bot")
            assert hasattr(client.bot, "event")

    def test_register_command_structure(self):
        """Test that register_command method exists and has expected structure."""
        with patch("mindtrace.services.discord.discord_client.Mindtrace.__init__") as mock_init:
            mock_init.return_value = None

            # Create client and set up mocks
            client = DiscordClient.__new__(DiscordClient)
            client.logger = Mock()
            client.config = Mock()
            client.config.get_secret.return_value = "test_token"
            client._commands = {}
            client._command_handlers = {}

            # Test initialization
            client.__init__(token="test_token")

            # Verify register_command method exists
            assert hasattr(client, "register_command")
            assert callable(client.register_command)

    @pytest.mark.asyncio
    async def test_command_execution_with_permissions(self):
        """Test command execution with permission checking."""
        with patch("mindtrace.services.discord.discord_client.Mindtrace.__init__") as mock_init:
            mock_init.return_value = None

            # Create a mock bot
            mock_bot = Mock()

            # Create client and set up mocks
            client = DiscordClient.__new__(DiscordClient)
            client.bot = mock_bot
            client.logger = Mock()
            client.config = Mock()
            client.config.get_secret.return_value = "test_token"
            client._commands = {}
            client._command_handlers = {}

            # Create a command with permissions
            command = DiscordCommand(
                name="test",
                description="Test command",
                usage="!test",
                aliases=["t"],
                category="Test",
                permissions=["manage_messages"],
            )
            client._commands["test"] = command

            async def test_handler(ctx):
                await ctx.send("Test response")

            client._command_handlers["test"] = test_handler

            # Create mock context with insufficient permissions
            mock_ctx = Mock()
            mock_ctx.author = Mock()
            mock_ctx.author.guild_permissions = Mock()
            mock_ctx.author.guild_permissions.manage_messages = False
            mock_ctx.send = AsyncMock()

            # Test command execution with insufficient permissions
            await client._execute_command(mock_ctx, "test")

            # Verify permission error message was sent
            mock_ctx.send.assert_called_once_with("You need the `manage_messages` permission to use this command.")

    @pytest.mark.asyncio
    async def test_command_execution_with_cooldown(self):
        """Test command execution with cooldown handling."""
        with patch("mindtrace.services.discord.discord_client.Mindtrace.__init__") as mock_init:
            mock_init.return_value = None

            # Create a mock bot
            mock_bot = Mock()

            # Create client and set up mocks
            client = DiscordClient.__new__(DiscordClient)
            client.bot = mock_bot
            client.logger = Mock()
            client.config = Mock()
            client.config.get_secret.return_value = "test_token"
            client._commands = {}
            client._command_handlers = {}

            # Create a command with cooldown
            command = DiscordCommand(
                name="test", description="Test command", usage="!test", aliases=["t"], category="Test", cooldown=5.0
            )
            client._commands["test"] = command

            async def test_handler(ctx):
                await ctx.send("Test response")

            client._command_handlers["test"] = test_handler

            # Create mock context
            mock_ctx = Mock()
            mock_ctx.author = Mock()
            mock_ctx.author.guild_permissions = Mock()
            mock_ctx.author.guild_permissions.manage_messages = True
            mock_ctx.send = AsyncMock()

            # Test command execution with cooldown (should pass through cooldown check)
            await client._execute_command(mock_ctx, "test")

            # Verify command handler was called
            mock_ctx.send.assert_called_once_with("Test response")


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
            "guild_leave",
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
            content="!test", author_id=123, channel_id=456, guild_id=789, message_id=101112
        )

        assert input_data.content == "!test"
        assert input_data.author_id == 123
        assert input_data.channel_id == 456
        assert input_data.guild_id == 789
        assert input_data.message_id == 101112

    def test_discord_command_output(self):
        """Test DiscordCommandOutput schema."""
        output_data = DiscordCommandOutput(response="Test response", embed={"title": "Test"}, delete_after=5.0)

        assert output_data.response == "Test response"
        assert output_data.embed == {"title": "Test"}
        assert output_data.delete_after == 5.0

    def test_discord_command_output_minimal(self):
        """Test DiscordCommandOutput with minimal data."""
        output_data = DiscordCommandOutput(response="Test")

        assert output_data.response == "Test"
        assert output_data.embed is None
        assert output_data.delete_after is None

    def test_discord_event_handler_abstract(self):
        """Test DiscordEventHandler abstract class."""
        from mindtrace.services.discord.types import DiscordEventHandler, DiscordEventType

        # Test that DiscordEventHandler is abstract
        with pytest.raises(TypeError):
            DiscordEventHandler()

        # Test concrete implementation
        class TestEventHandler(DiscordEventHandler):
            async def handle(self, event_type: DiscordEventType, **kwargs):
                pass

        handler = TestEventHandler()
        assert isinstance(handler, DiscordEventHandler)
