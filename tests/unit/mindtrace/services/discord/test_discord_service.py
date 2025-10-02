"""
Unit tests for the Discord service implementation.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest

from mindtrace.services.discord.discord_service import DiscordService
from mindtrace.services.discord.types import (
    DiscordCommandInput,
    DiscordCommandOutput,
    DiscordCommandsOutput,
    DiscordStatusOutput,
)


class TestDiscordService:
    """Test DiscordService class."""

    @pytest.fixture
    def discord_service(self):
        """Create a DiscordService instance for testing."""
        with patch("mindtrace.services.discord.discord_service.DiscordClient") as mock_client:
            mock_client.return_value.bot = Mock()
            mock_client.return_value.bot.user = Mock()
            mock_client.return_value.bot.user.name = "TestBot"
            mock_client.return_value.bot.guilds = []
            mock_client.return_value.bot.users = []
            mock_client.return_value.bot.latency = 0.1
            mock_client.return_value.bot.status = "online"
            mock_client.return_value._commands = {}

            # Mock the command tree to return an iterable
            mock_command = Mock()
            mock_command.name = "test"
            mock_command.description = "Test command"
            mock_command.usage = "!test"
            mock_command.aliases = ["t"]
            mock_command.category = "General"
            mock_command.enabled = True
            mock_command.hidden = False
            mock_command.parameters = []
            mock_command.callback = Mock()

            mock_client.return_value.bot.tree = Mock()
            mock_client.return_value.bot.tree.get_commands.return_value = [mock_command]

            service = DiscordService(token="test_token")
            return service

    def test_discord_service_initialization(self, discord_service):
        """Test DiscordService initialization."""
        assert discord_service.discord_client is not None
        assert discord_service._bot_task is None

    def test_get_bot_status_not_started(self, discord_service):
        """Test bot status when bot is not started."""
        discord_service.discord_client.bot = None

        status = discord_service.get_bot_status()

        assert isinstance(status, DiscordStatusOutput)
        assert status.bot_name is None
        assert status.guild_count == 0
        assert status.user_count == 0
        assert status.latency == 0.0
        assert status.status == "not_started"

    def test_get_bot_status_started(self, discord_service):
        """Test bot status when bot is started."""
        status = discord_service.get_bot_status()

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

        commands = discord_service.get_commands()

        assert isinstance(commands, DiscordCommandsOutput)
        assert len(commands.commands) == 1
        assert commands.commands[0]["name"] == "test"
        assert commands.commands[0]["description"] == "Test command"

    @pytest.mark.asyncio
    async def test_execute_command(self, discord_service):
        """Test command execution endpoint."""
        input_data = DiscordCommandInput(
            content="!test", author_id=123, channel_id=456, guild_id=789, message_id=101112
        )

        # Mock the command callback to return a response
        mock_interaction = Mock()
        mock_interaction.response = Mock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.followup = Mock()
        mock_interaction.followup.send = AsyncMock()

        # Mock the _create_minimal_interaction method to return our mock
        with patch.object(discord_service, "_create_minimal_interaction", return_value=mock_interaction):
            output = await discord_service.execute_command(input_data)

        assert isinstance(output, DiscordCommandOutput)
        # The command should be found and executed
        assert "Command executed successfully" in output.response or "test" in output.response

    def test_register_command_delegation(self, discord_service):
        """Test that register_command delegates to discord_client."""
        with patch.object(discord_service.discord_client, "register_command") as mock_register:

            def test_handler(x):
                return None

            discord_service.register_command(
                name="test", description="Test command", usage="!test", handler=test_handler
            )

            mock_register.assert_called_once_with(
                name="test", description="Test command", usage="!test", handler=test_handler
            )

    def test_register_event_handler_delegation(self, discord_service):
        """Test that register_event_handler delegates to discord_client."""
        with patch.object(discord_service.discord_client, "register_event_handler") as mock_register:
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
        with patch.object(discord_service.discord_client, "start_bot", new_callable=AsyncMock) as mock_start:
            await discord_service._run_bot()

            mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_bot_error(self, discord_service):
        """Test bot running with error."""
        with patch.object(discord_service.discord_client, "start_bot", new_callable=AsyncMock) as mock_start:
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
        with patch.object(discord_service.discord_client, "stop_bot", new_callable=AsyncMock) as mock_stop:
            await discord_service.shutdown_cleanup()

            mock_task.cancel.assert_called_once()
            mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_cleanup_no_bot_task(self, discord_service):
        """Test shutdown cleanup when no bot task exists."""
        discord_service._bot_task = None

        with patch.object(discord_service.discord_client, "stop_bot", new_callable=AsyncMock) as mock_stop:
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

        with patch.object(discord_service.discord_client, "stop_bot", new_callable=AsyncMock) as mock_stop:
            mock_stop.side_effect = Exception("Stop error")

            # Should not raise exception
            await discord_service.shutdown_cleanup()

            mock_task.cancel.assert_called_once()
            mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_command_bot_not_connected(self, discord_service):
        """Test command execution when bot is not connected."""
        discord_service.discord_client.bot = None

        input_data = DiscordCommandInput(
            content="!test", author_id=123, channel_id=456, guild_id=789, message_id=101112
        )

        output = await discord_service.execute_command(input_data)

        assert isinstance(output, DiscordCommandOutput)
        assert "Bot is not connected" in output.response

    @pytest.mark.asyncio
    async def test_execute_command_not_found(self, discord_service):
        """Test command execution when command is not found."""
        # Mock empty command tree
        discord_service.discord_client.bot.tree.get_commands.return_value = []

        input_data = DiscordCommandInput(
            content="/nonexistent", author_id=123, channel_id=456, guild_id=789, message_id=101112
        )

        output = await discord_service.execute_command(input_data)

        assert isinstance(output, DiscordCommandOutput)
        assert "Command '/nonexistent' not found" in output.response
        assert "Available commands:" in output.response

    @pytest.mark.asyncio
    async def test_execute_command_with_parameters(self, discord_service):
        """Test command execution with parameters."""
        # Mock command with parameters
        mock_command = Mock()
        mock_command.name = "roll"
        mock_command.parameters = [Mock(name="sides", type=1)]  # 1 = integer type
        mock_command.callback = AsyncMock()

        discord_service.discord_client.bot.tree.get_commands.return_value = [mock_command]

        input_data = DiscordCommandInput(
            content="/roll 20", author_id=123, channel_id=456, guild_id=789, message_id=101112
        )

        # Mock the interaction creation
        mock_interaction = Mock()
        mock_interaction.response = Mock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.followup = Mock()
        mock_interaction.followup.send = AsyncMock()

        with patch.object(discord_service, "_create_minimal_interaction", return_value=mock_interaction):
            output = await discord_service.execute_command(input_data)

        assert isinstance(output, DiscordCommandOutput)
        # The command should be found and executed
        assert "Command '/roll' not found" not in output.response

    def test_get_default_values(self, discord_service):
        """Test default value handling."""
        payload = DiscordCommandInput(content="!test", author_id=None, channel_id=None, guild_id=789, message_id=None)

        defaults = discord_service._get_default_values(payload, "test")

        assert defaults.author_id == 0
        assert defaults.channel_id == 0
        assert defaults.guild_id == 789
        assert defaults.message_id == 0

    def test_get_default_values_with_warnings(self, discord_service):
        """Test default value handling with warning logging."""
        payload = DiscordCommandInput(content="!info", author_id=None, channel_id=None, guild_id=None, message_id=None)

        with patch.object(discord_service.logger, "warning") as mock_warning:
            discord_service._get_default_values(payload, "info")

            # Should log warnings for missing values
            assert mock_warning.call_count >= 3  # author_id, channel_id, message_id
            assert any("author_id not provided" in str(call) for call in mock_warning.call_args_list)
            assert any("channel_id not provided" in str(call) for call in mock_warning.call_args_list)
            assert any("message_id not provided" in str(call) for call in mock_warning.call_args_list)

    def test_parse_command_parameters(self, discord_service):
        """Test command parameter parsing."""
        # Mock command with parameters
        mock_param = Mock()
        mock_param.name = "sides"
        mock_param.type = discord.AppCommandOptionType.integer  # integer type
        mock_param.default = None

        mock_command = Mock()
        mock_command.parameters = [mock_param]

        content = "!roll 20"
        params = discord_service._parse_command_parameters(content, mock_command)

        assert params["sides"] == 20  # The actual implementation converts to the correct type

    def test_parse_command_parameters_with_defaults(self, discord_service):
        """Test command parameter parsing with defaults."""
        # Mock command with parameters
        mock_param = Mock()
        mock_param.name = "sides"
        mock_param.type = discord.AppCommandOptionType.integer  # integer type
        mock_param.default = 6

        mock_command = Mock()
        mock_command.parameters = [mock_param]

        content = "!roll"  # No parameters provided
        params = discord_service._parse_command_parameters(content, mock_command)

        assert params["sides"] == 6  # Should use the parameter's default value

    def test_parse_command_parameters_conversion_error(self, discord_service):
        """Test command parameter parsing with conversion error."""
        # Mock command with parameters
        mock_param = Mock()
        mock_param.name = "sides"
        mock_param.type = discord.AppCommandOptionType.integer  # integer type
        mock_param.default = None

        mock_command = Mock()
        mock_command.parameters = [mock_param]

        content = "!roll invalid"  # Invalid integer
        params = discord_service._parse_command_parameters(content, mock_command)

        assert params["sides"] is None  # The actual implementation returns None for conversion errors

    def test_get_python_type_from_discord_type(self, discord_service):
        """Test Discord type to Python type conversion."""
        import discord

        # Test various Discord types
        assert discord_service._get_python_type_from_discord_type(discord.AppCommandOptionType.string) is str
        assert discord_service._get_python_type_from_discord_type(discord.AppCommandOptionType.integer) is int
        assert discord_service._get_python_type_from_discord_type(discord.AppCommandOptionType.number) is float
        assert discord_service._get_python_type_from_discord_type(discord.AppCommandOptionType.boolean) is bool
        assert discord_service._get_python_type_from_discord_type(discord.AppCommandOptionType.user) is int
        assert discord_service._get_python_type_from_discord_type(discord.AppCommandOptionType.channel) is int
        assert discord_service._get_python_type_from_discord_type(discord.AppCommandOptionType.role) is int
        assert discord_service._get_python_type_from_discord_type(discord.AppCommandOptionType.mentionable) is int
        assert discord_service._get_python_type_from_discord_type(discord.AppCommandOptionType.attachment) is str

        # Test unknown type (should default to str)
        unknown_type = Mock()
        assert discord_service._get_python_type_from_discord_type(unknown_type) is str

    def test_create_minimal_interaction(self, discord_service):
        """Test minimal interaction creation."""
        payload = DiscordCommandInput(content="!test", author_id=123, channel_id=456, guild_id=789, message_id=101112)

        interaction = discord_service._create_minimal_interaction(payload)

        assert interaction.user.id == 123
        assert interaction.user.mention == "<@123>"
        assert interaction.user.display_name == "User123"
        assert interaction.guild.id == 789
        assert interaction.channel.id == 456
        assert interaction.message_id == 101112
        assert hasattr(interaction.response, "send_message")
        assert hasattr(interaction.followup, "send")

    def test_create_minimal_interaction_no_guild(self, discord_service):
        """Test minimal interaction creation without guild."""
        payload = DiscordCommandInput(content="!test", author_id=123, channel_id=456, guild_id=None, message_id=101112)

        interaction = discord_service._create_minimal_interaction(payload)

        assert interaction.user.id == 123
        assert interaction.guild is None
        assert interaction.channel.id == 456

    def test_create_minimal_interaction_no_author_id(self, discord_service):
        """Test minimal interaction creation without author_id."""
        payload = DiscordCommandInput(content="!test", author_id=None, channel_id=456, guild_id=789, message_id=101112)

        interaction = discord_service._create_minimal_interaction(payload)

        assert interaction.user.id is None
        assert interaction.user.mention == "<@0>"
        assert interaction.user.display_name == "API User"

    @pytest.mark.asyncio
    async def test_execute_command_with_response_send_message(self, discord_service):
        """Test command execution with response.send_message called."""
        # Mock command
        mock_command = Mock()
        mock_command.name = "test"
        mock_command.parameters = []
        mock_command.callback = AsyncMock()

        discord_service.discord_client.bot.tree.get_commands.return_value = [mock_command]

        # Mock interaction with send_message called
        mock_interaction = Mock()
        mock_interaction.response = Mock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.response.send_message.called = True
        mock_interaction.response.send_message.call_args = (("Test response",), {})
        mock_interaction.followup = Mock()
        mock_interaction.followup.send = AsyncMock()
        mock_interaction.followup.send.called = False

        with patch.object(discord_service, "_create_minimal_interaction", return_value=mock_interaction):
            input_data = DiscordCommandInput(content="/test")
            output = await discord_service.execute_command(input_data)

        # The command should be found and executed
        assert "Command '/test' not found" not in output.response

    @pytest.mark.asyncio
    async def test_execute_command_with_followup_send(self, discord_service):
        """Test command execution with followup.send called."""
        # Mock command
        mock_command = Mock()
        mock_command.name = "test"
        mock_command.parameters = []
        mock_command.callback = AsyncMock()

        discord_service.discord_client.bot.tree.get_commands.return_value = [mock_command]

        # Mock interaction with followup.send called
        mock_interaction = Mock()
        mock_interaction.response = Mock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.response.send_message.called = False
        mock_interaction.followup = Mock()
        mock_interaction.followup.send = AsyncMock()
        mock_interaction.followup.send.called = True
        mock_interaction.followup.send.call_args = (("Followup response",), {})

        with patch.object(discord_service, "_create_minimal_interaction", return_value=mock_interaction):
            input_data = DiscordCommandInput(content="/test")
            output = await discord_service.execute_command(input_data)

        # The command should be found and executed
        assert "Command '/test' not found" not in output.response

    @pytest.mark.asyncio
    async def test_execute_command_with_exception(self, discord_service):
        """Test command execution with exception."""
        # Mock command that raises exception
        mock_command = Mock()
        mock_command.name = "test"
        mock_command.parameters = []
        mock_command.callback = AsyncMock(side_effect=Exception("Test error"))

        discord_service.discord_client.bot.tree.get_commands.return_value = [mock_command]

        mock_interaction = Mock()
        mock_interaction.response = Mock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.followup = Mock()
        mock_interaction.followup.send = AsyncMock()

        with patch.object(discord_service, "_create_minimal_interaction", return_value=mock_interaction):
            with patch.object(discord_service.logger, "error") as mock_logger:
                input_data = DiscordCommandInput(content="/test")
                output = await discord_service.execute_command(input_data)

        # The command should be found and executed, but with an error
        assert "Command '/!test' not found" not in output.response
        assert "Error executing command: Test error" in output.response
        mock_logger.assert_called_once()

    @pytest.mark.asyncio
    async def test_startup_already_started(self, discord_service):
        """Test startup when already started."""
        # Set up a mock task
        mock_task = Mock()
        discord_service._bot_task = mock_task

        await discord_service.startup()

        # Should not create a new task
        assert discord_service._bot_task is mock_task

    @pytest.mark.asyncio
    async def test_run_bot_success(self, discord_service):
        """Test successful bot running."""
        with patch.object(discord_service.discord_client, "start_bot", new_callable=AsyncMock) as mock_start:
            await discord_service._run_bot()
            mock_start.assert_called_once()

    def test_launch_context_manager(self, discord_service):
        """Test DiscordService.launch context manager."""
        # Test the launch method returns a connection manager
        cm = discord_service.launch()
        assert cm is not None

        # Test that the context manager can be used
        with cm:
            assert cm is not None

    def test_parse_command_parameters_empty_content(self, discord_service):
        """Test command parameter parsing with empty content."""
        mock_command = Mock()
        mock_command.parameters = []

        content = ""
        params = discord_service._parse_command_parameters(content, mock_command)

        assert params == {}

    def test_parse_command_parameters_whitespace_content(self, discord_service):
        """Test command parameter parsing with whitespace-only content."""
        mock_command = Mock()
        mock_command.parameters = []

        content = "   \n\t  "
        params = discord_service._parse_command_parameters(content, mock_command)

        assert params == {}

    def test_parse_command_parameters_conversion_error_with_default(self, discord_service):
        """Test command parameter parsing with conversion error and default value."""
        # Mock command with parameters that have defaults
        mock_param = Mock()
        mock_param.name = "sides"
        mock_param.type = discord.AppCommandOptionType.integer  # integer type
        mock_param.default = 20

        mock_command = Mock()
        mock_command.parameters = [mock_param]

        content = "/roll invalid"  # Invalid integer
        params = discord_service._parse_command_parameters(content, mock_command)

        assert params["sides"] == 20  # The actual implementation uses the default value for conversion errors

    def test_parse_command_parameters_conversion_error_no_default_int(self, discord_service):
        """Test command parameter parsing with conversion error, no default, int type."""
        # Mock command with parameters that have no defaults
        mock_param = Mock()
        mock_param.name = "sides"
        mock_param.type = discord.AppCommandOptionType.integer  # integer type
        mock_param.default = None

        mock_command = Mock()
        mock_command.parameters = [mock_param]

        content = "/roll invalid"  # Invalid integer
        params = discord_service._parse_command_parameters(content, mock_command)

        assert params["sides"] is None  # The actual implementation returns None for conversion errors

    def test_parse_command_parameters_conversion_error_no_default_str(self, discord_service):
        """Test command parameter parsing with conversion error, no default, str type."""
        # Mock command with parameters that have no defaults
        mock_param = Mock()
        mock_param.name = "message"
        mock_param.type = 3  # string type
        mock_param.default = None

        mock_command = Mock()
        mock_command.parameters = [mock_param]

        content = "/say"  # No parameters provided
        params = discord_service._parse_command_parameters(content, mock_command)

        assert params["message"] is None  # Should return None for missing parameters

    def test_parse_command_parameters_conversion_error_no_default_other(self, discord_service):
        """Test command parameter parsing with conversion error, no default, other type."""
        # Mock command with parameters that have no defaults
        mock_param = Mock()
        mock_param.name = "value"
        mock_param.type = 10  # unknown type
        mock_param.default = None

        mock_command = Mock()
        mock_command.parameters = [mock_param]

        content = "/test"  # No parameters provided
        params = discord_service._parse_command_parameters(content, mock_command)

        assert params["value"] is None  # The actual implementation returns None for no params

    def test_parse_command_parameters_has_default_attribute(self, discord_service):
        """Test command parameter parsing with hasattr check for default."""
        # Mock command with parameters that don't have default attribute
        mock_param = Mock()
        mock_param.name = "sides"
        mock_param.type = discord.AppCommandOptionType.integer  # Use the actual enum
        # Remove the default attribute that Mock creates by default
        del mock_param.default

        mock_command = Mock()
        mock_command.parameters = [mock_param]

        content = "/roll"  # No parameters provided
        params = discord_service._parse_command_parameters(content, mock_command)

        assert params["sides"] is None  # The actual implementation returns None for missing parameters

    @pytest.mark.asyncio
    async def test_execute_command_no_response_methods_called(self, discord_service):
        """Test command execution when neither response method is called."""
        # Mock command
        mock_command = Mock()
        mock_command.name = "test"
        mock_command.parameters = []
        mock_command.callback = AsyncMock()

        discord_service.discord_client.bot.tree.get_commands.return_value = [mock_command]

        # Mock interaction with no response methods called
        mock_interaction = Mock()
        mock_interaction.response = Mock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.response.send_message.called = False
        mock_interaction.followup = Mock()
        mock_interaction.followup.send = AsyncMock()
        mock_interaction.followup.send.called = False

        with patch.object(discord_service, "_create_minimal_interaction", return_value=mock_interaction):
            input_data = DiscordCommandInput(content="/test")
            output = await discord_service.execute_command(input_data)

        # Should return default success message
        assert output.response == "Command executed successfully"

    def test_get_python_type_from_discord_type_unknown(self, discord_service):
        """Test Discord type to Python type conversion with unknown type."""
        # Test with a completely unknown type
        unknown_type = Mock()
        unknown_type.value = 999  # Some unknown value

        result = discord_service._get_python_type_from_discord_type(unknown_type)
        assert result is str  # Should default to str
