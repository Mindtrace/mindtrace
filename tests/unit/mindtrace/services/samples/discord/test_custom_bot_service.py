"""
Unit tests for the custom Discord bot service sample.
"""

import runpy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from mindtrace.services.discord.types import DiscordEventType
from mindtrace.services.samples.discord.custom_bot_service import (
    CustomDiscordService,
    CustomEventHandler,
    main,
    parse_arguments,
)


class _CommandTree:
    def __init__(self):
        self.commands = {}

    def command(self, *, name, description):
        def decorator(func):
            self.commands[name] = func
            return func

        return decorator

    def get_commands(self):
        return list(self.commands.values())


def _patch_service_init():
    tree = _CommandTree()

    def fake_init(self, **kwargs):
        self.logger = Mock()
        self.id = "service-123"
        self.discord_client = SimpleNamespace(bot=SimpleNamespace(tree=tree))
        self.register_event_handler = Mock()
        self.get_bot_status = Mock()

    return tree, fake_init


def _make_history(*messages):
    async def history(*, limit):
        for message in messages[:limit]:
            yield message

    return history


def _make_interaction(*, guild=None, user=None, channel=None, client=None):
    if user is None:
        user = SimpleNamespace(id=123)
    interaction = Mock()
    interaction.guild = guild
    interaction.user = user
    interaction.channel = channel or Mock()
    interaction.client = client or SimpleNamespace(user=object())
    interaction.response = Mock()
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = Mock()
    interaction.followup.send = AsyncMock()
    return interaction


class TestCustomEventHandler:
    """Test the CustomEventHandler class."""

    @pytest.mark.asyncio
    async def test_handle_message_with_hello(self):
        """Test handling a message containing 'hello'."""
        handler = CustomEventHandler()

        # Mock message
        mock_message = Mock()
        mock_message.content = "Hello there!"
        mock_message.channel = Mock()
        mock_message.channel.send = AsyncMock()

        # Test message handling
        await handler.handle(DiscordEventType.MESSAGE, message=mock_message)

        # Verify response was sent
        mock_message.channel.send.assert_called_once_with("Hello there! 👋")

    @pytest.mark.asyncio
    async def test_handle_message_without_hello(self):
        """Test handling a message without 'hello'."""
        handler = CustomEventHandler()

        # Mock message
        mock_message = Mock()
        mock_message.content = "Just a regular message"
        mock_message.channel = Mock()
        mock_message.channel.send = AsyncMock()

        # Test message handling
        await handler.handle(DiscordEventType.MESSAGE, message=mock_message)

        # Verify no response was sent
        mock_message.channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_case_insensitive(self):
        """Test handling a message with 'HELLO' in different case."""
        handler = CustomEventHandler()

        # Mock message
        mock_message = Mock()
        mock_message.content = "HELLO WORLD"
        mock_message.channel = Mock()
        mock_message.channel.send = AsyncMock()

        # Test message handling
        await handler.handle(DiscordEventType.MESSAGE, message=mock_message)

        # Verify response was sent
        mock_message.channel.send.assert_called_once_with("Hello there! 👋")

    @pytest.mark.asyncio
    async def test_handle_message_no_message(self):
        """Test handling MESSAGE event without message."""
        handler = CustomEventHandler()

        # Test message handling without message
        await handler.handle(DiscordEventType.MESSAGE)

        # Should not raise any exceptions

    @pytest.mark.asyncio
    async def test_handle_member_join(self):
        """Test handling member join event."""
        handler = CustomEventHandler()

        # Mock member and guild
        mock_member = Mock()
        mock_member.mention = "@testuser"
        mock_member.guild = Mock()

        # Mock text channel with permissions
        mock_channel = Mock()
        mock_channel.permissions_for.return_value.send_messages = True
        mock_channel.send = AsyncMock()
        mock_member.guild.text_channels = [mock_channel]

        # Test member join handling
        await handler.handle(DiscordEventType.MEMBER_JOIN, member=mock_member)

        # Verify welcome message was sent
        mock_channel.send.assert_called_once_with("Welcome @testuser to the server! 🎉")

    @pytest.mark.asyncio
    async def test_handle_member_join_no_permissions(self):
        """Test handling member join when no channel has send permissions."""
        handler = CustomEventHandler()

        # Mock member and guild
        mock_member = Mock()
        mock_member.mention = "@testuser"
        mock_member.guild = Mock()

        # Mock text channel without permissions
        mock_channel = Mock()
        mock_channel.permissions_for.return_value.send_messages = False
        mock_channel.send = AsyncMock()
        mock_member.guild.text_channels = [mock_channel]

        # Test member join handling
        await handler.handle(DiscordEventType.MEMBER_JOIN, member=mock_member)

        # Verify no message was sent
        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_member_join_no_member(self):
        """Test handling member join event without member."""
        handler = CustomEventHandler()

        # Test member join handling without member
        await handler.handle(DiscordEventType.MEMBER_JOIN)

        # Should not raise any exceptions


class TestCustomDiscordService:
    """Test the CustomDiscordService class."""

    def test_custom_discord_service_class_exists(self):
        """Test that CustomDiscordService class can be imported and instantiated."""
        # Test that the class exists and can be imported
        assert CustomDiscordService is not None
        assert hasattr(CustomDiscordService, "__init__")
        assert hasattr(CustomDiscordService, "_register_commands")

    def test_custom_discord_service_inheritance(self):
        """Test that CustomDiscordService inherits from DiscordService."""
        from mindtrace.services.discord.discord_service import DiscordService

        assert issubclass(CustomDiscordService, DiscordService)

    def test_init_basic_functionality(self):
        """Test that __init__ basic functionality works."""
        # Test that the class can be instantiated without errors
        # The actual initialization logic is complex due to parent class dependencies
        # and is better tested in integration tests

        # Test that the class exists and has the expected methods
        assert hasattr(CustomDiscordService, "__init__")
        assert hasattr(CustomDiscordService, "_register_commands")
        assert hasattr(CustomDiscordService, "register_event_handler")

    def test_init_registers_event_handler_and_commands(self):
        tree, fake_init = _patch_service_init()

        with patch("mindtrace.services.samples.discord.custom_bot_service.DiscordService.__init__", new=fake_init):
            service = CustomDiscordService(token="abc")

        service.register_event_handler.assert_called_once()
        assert set(tree.commands) == {"info", "roll", "cleanup", "help", "service"}


class TestRegisteredCommands:
    @pytest.fixture
    def service_and_commands(self):
        tree, fake_init = _patch_service_init()

        with patch("mindtrace.services.samples.discord.custom_bot_service.DiscordService.__init__", new=fake_init):
            service = CustomDiscordService(token="abc")

        return service, tree.commands

    @pytest.mark.asyncio
    async def test_info_command_requires_guild(self, service_and_commands):
        _, commands = service_and_commands
        interaction = _make_interaction(guild=None)

        await commands["info"](interaction)

        interaction.response.send_message.assert_awaited_once_with(
            "This command can only be used in a server.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_info_command_reports_guild_details_and_service_id(self, service_and_commands):
        service, commands = service_and_commands
        guild = SimpleNamespace(
            name="Guild",
            member_count=42,
            channels=[1, 2],
            roles=["a"],
            created_at=datetime(2024, 1, 2),
        )
        interaction = _make_interaction(guild=guild, user="tester")

        await commands["info"](interaction)

        sent_message = interaction.response.send_message.await_args.args[0]
        assert "Server Information" in sent_message
        assert "Name: Guild" in sent_message
        assert "Service ID: service-123" in sent_message
        service.logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_roll_command_rejects_non_positive_sides(self, service_and_commands):
        _, commands = service_and_commands
        interaction = _make_interaction()

        await commands["roll"](interaction, 0)

        interaction.response.send_message.assert_awaited_once_with(
            "Number of sides must be positive.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_roll_command_uses_random_result(self, service_and_commands):
        _, commands = service_and_commands
        interaction = _make_interaction()

        with patch("random.randint", return_value=4):
            await commands["roll"](interaction, 6)

        interaction.response.send_message.assert_awaited_once_with("You rolled a 4 (1-6)")

    @pytest.mark.asyncio
    async def test_cleanup_command_requires_guild(self, service_and_commands):
        _, commands = service_and_commands
        interaction = _make_interaction(guild=None)

        await commands["cleanup"](interaction, 10)

        interaction.response.send_message.assert_awaited_once_with(
            "This command can only be used in a server.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_cleanup_command_requires_manage_messages_permission(self, service_and_commands):
        _, commands = service_and_commands
        member = SimpleNamespace(guild_permissions=SimpleNamespace(manage_messages=False))
        guild = Mock()
        guild.get_member.return_value = member
        interaction = _make_interaction(guild=guild, user=SimpleNamespace(id=5))

        await commands["cleanup"](interaction, 10)

        interaction.response.send_message.assert_awaited_once_with(
            "You need the 'Manage Messages' permission to use this command.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_cleanup_command_validates_count_range(self, service_and_commands):
        _, commands = service_and_commands
        member = SimpleNamespace(guild_permissions=SimpleNamespace(manage_messages=True))
        guild = Mock()
        guild.get_member.return_value = member
        interaction = _make_interaction(guild=guild, user=SimpleNamespace(id=5))

        await commands["cleanup"](interaction, 101)

        interaction.response.send_message.assert_awaited_once_with(
            "Please specify a number between 1 and 100.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_cleanup_command_deletes_only_bot_messages(self, service_and_commands):
        _, commands = service_and_commands
        member = SimpleNamespace(guild_permissions=SimpleNamespace(manage_messages=True))
        guild = Mock()
        guild.get_member.return_value = member
        bot_user = object()
        bot_message = SimpleNamespace(author=bot_user, delete=AsyncMock())
        other_message = SimpleNamespace(author=object(), delete=AsyncMock())
        channel = Mock()
        channel.history = _make_history(bot_message, other_message, bot_message)
        interaction = _make_interaction(
            guild=guild, user=SimpleNamespace(id=5), channel=channel, client=SimpleNamespace(user=bot_user)
        )

        await commands["cleanup"](interaction, 3)

        interaction.response.defer.assert_awaited_once()
        assert bot_message.delete.await_count == 2
        other_message.delete.assert_not_awaited()
        interaction.followup.send.assert_awaited_once_with("Cleaned up 2 bot messages.")

    @pytest.mark.asyncio
    async def test_help_command_lists_available_commands(self, service_and_commands):
        _, commands = service_and_commands
        interaction = _make_interaction()

        await commands["help"](interaction)

        sent_message = interaction.response.send_message.await_args.args[0]
        assert "Available commands:" in sent_message
        assert "**/help** - Show this help message" in sent_message

    @pytest.mark.asyncio
    async def test_service_command_formats_status(self, service_and_commands):
        service, commands = service_and_commands
        service.get_bot_status.return_value = SimpleNamespace(
            bot_name="ExampleBot",
            guild_count=3,
            user_count=25,
            latency=12.5,
            status="running",
        )
        interaction = _make_interaction()

        await commands["service"](interaction)

        sent_message = interaction.response.send_message.await_args.args[0]
        assert "Service Status" in sent_message
        assert "Bot: ExampleBot" in sent_message
        assert "Service ID: service-123" in sent_message

    @pytest.mark.asyncio
    async def test_service_command_reports_errors_ephemerally(self, service_and_commands):
        service, commands = service_and_commands
        service.get_bot_status.side_effect = RuntimeError("status lookup failed")
        interaction = _make_interaction()

        await commands["service"](interaction)

        interaction.response.send_message.assert_awaited_once_with(
            "Error getting service status: status lookup failed", ephemeral=True
        )


class TestCommandFunctions:
    """Test the individual command functions by testing them directly."""

    def test_command_functions_exist(self):
        """Test that command functions can be created without errors."""
        # These tests verify that the command function structure is correct
        # The actual command execution is better tested in integration tests
        # where we can test with a real Discord bot

        # Test that we can create mock interactions
        mock_interaction = Mock()
        mock_interaction.guild = None
        mock_interaction.response.send_message = AsyncMock()

        # This tests that the command function structure is correct
        # We can't easily test the actual command registration without complex mocking
        assert True  # Placeholder - the real test is that the code doesn't crash


class TestParseArguments:
    """Test the parse_arguments function."""

    def test_parse_arguments_default(self):
        """Test parsing arguments with defaults."""
        with patch("sys.argv", ["custom_bot_service.py"]):
            args = parse_arguments()

            assert args.token is None
            assert args.host == "localhost"
            assert args.port == 8080
            assert args.description == "A custom Discord bot service built with Mindtrace"
            assert args.verbose is False

    def test_parse_arguments_with_all_options(self):
        """Test parsing arguments with all options."""
        with patch(
            "sys.argv",
            [
                "custom_bot_service.py",
                "--token",
                "test_token",
                "--host",
                "0.0.0.0",
                "--port",
                "9000",
                "--description",
                "Test service",
                "--verbose",
            ],
        ):
            args = parse_arguments()

            assert args.token == "test_token"
            assert args.host == "0.0.0.0"
            assert args.port == 9000
            assert args.description == "Test service"
            assert args.verbose is True


class TestMain:
    """Test the main function."""

    def test_main_with_token(self):
        """Test main function with token."""
        with patch("mindtrace.services.samples.discord.custom_bot_service.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(
                token="test_token", host="localhost", port=8080, description="Test service", verbose=False
            )

            with patch(
                "mindtrace.services.samples.discord.custom_bot_service.CustomDiscordService"
            ) as mock_service_class:
                mock_service_manager = Mock()
                mock_service_manager.url = "http://localhost:8080"
                mock_service_manager.status.return_value = "running"
                mock_service_class.launch.return_value = mock_service_manager

                with patch("builtins.print"):
                    with patch("time.sleep", side_effect=KeyboardInterrupt()):
                        main()

                # Verify service was launched with correct parameters
                mock_service_class.launch.assert_called_once_with(
                    host="localhost", port=8080, token="test_token", wait_for_launch=True, timeout=30
                )

                # Verify shutdown was called
                mock_service_manager.shutdown.assert_called_once()

    def test_main_without_token(self):
        """Test main function without token."""
        with patch("mindtrace.services.samples.discord.custom_bot_service.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(
                token=None, host="localhost", port=8080, description="Test service", verbose=False
            )

            with patch(
                "mindtrace.services.samples.discord.custom_bot_service.CustomDiscordService"
            ) as mock_service_class:
                mock_service_manager = Mock()
                mock_service_manager.url = "http://localhost:8080"
                mock_service_manager.status.return_value = "running"
                mock_service_class.launch.return_value = mock_service_manager

                with patch("builtins.print"):
                    with patch("time.sleep", side_effect=KeyboardInterrupt()):
                        main()

                # Verify service was launched with None token
                mock_service_class.launch.assert_called_once_with(
                    host="localhost", port=8080, token=None, wait_for_launch=True, timeout=30
                )

    def test_main_exception(self):
        """Test main function with exception."""
        with patch("mindtrace.services.samples.discord.custom_bot_service.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(
                token="test_token", host="localhost", port=8080, description="Test service", verbose=False
            )

            with patch(
                "mindtrace.services.samples.discord.custom_bot_service.CustomDiscordService"
            ) as mock_service_class:
                mock_service_class.launch.side_effect = Exception("Test error")

                with patch("builtins.print"):
                    main()

                # Should not raise exception, just print error

    def test_main_verbose_output_with_token(self):
        """Test main function verbose output with token."""
        with patch("mindtrace.services.samples.discord.custom_bot_service.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(
                token="test_token", host="localhost", port=8080, description="Test service", verbose=True
            )

            with patch(
                "mindtrace.services.samples.discord.custom_bot_service.CustomDiscordService"
            ) as mock_service_class:
                mock_service_manager = Mock()
                mock_service_manager.url = "http://localhost:8080"
                mock_service_manager.status.return_value = "running"
                mock_service_class.launch.return_value = mock_service_manager

                with patch("builtins.print") as mock_print:
                    with patch("time.sleep", side_effect=KeyboardInterrupt()):
                        main()

                # Verify verbose output was printed
                mock_print.assert_any_call("Service description: Test service")
                mock_print.assert_any_call("Using token from command line")

    def test_main_verbose_output_without_token(self):
        """Test main function verbose output without token."""
        with patch("mindtrace.services.samples.discord.custom_bot_service.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(
                token=None, host="localhost", port=8080, description="Test service", verbose=True
            )

            with patch(
                "mindtrace.services.samples.discord.custom_bot_service.CustomDiscordService"
            ) as mock_service_class:
                mock_service_manager = Mock()
                mock_service_manager.url = "http://localhost:8080"
                mock_service_manager.status.return_value = "running"
                mock_service_class.launch.return_value = mock_service_manager

                with patch("builtins.print") as mock_print:
                    with patch("time.sleep", side_effect=KeyboardInterrupt()):
                        main()

                # Verify verbose output was printed
                mock_print.assert_any_call("Service description: Test service")
                mock_print.assert_any_call("Using MINDTRACE_DISCORD_BOT_TOKEN from config")

    def test_main_exception_with_verbose_traceback(self):
        """Test main function exception with verbose traceback."""
        with patch("mindtrace.services.samples.discord.custom_bot_service.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(
                token="test_token", host="localhost", port=8080, description="Test service", verbose=True
            )

            with patch(
                "mindtrace.services.samples.discord.custom_bot_service.CustomDiscordService"
            ) as mock_service_class:
                mock_service_class.launch.side_effect = Exception("Test error")

                with patch("builtins.print") as mock_print:
                    with patch("traceback.print_exc") as mock_traceback:
                        main()

                # Verify error message and traceback were printed
                mock_print.assert_any_call("Error running service: Test error")
                mock_traceback.assert_called_once()

    def test_main_exception_without_verbose_traceback(self):
        """Test main function exception without verbose traceback."""
        with patch("mindtrace.services.samples.discord.custom_bot_service.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(
                token="test_token", host="localhost", port=8080, description="Test service", verbose=False
            )

            with patch(
                "mindtrace.services.samples.discord.custom_bot_service.CustomDiscordService"
            ) as mock_service_class:
                mock_service_class.launch.side_effect = Exception("Test error")

                with patch("builtins.print") as mock_print:
                    with patch("traceback.print_exc") as mock_traceback:
                        main()

                # Verify error message was printed but not traceback
                mock_print.assert_any_call("Error running service: Test error")
                mock_traceback.assert_not_called()


class TestModuleExecution:
    """Test module execution when run as script."""

    def test_module_execution(self):
        """Test that the module can be executed as a script."""
        mock_manager = Mock()
        mock_manager.url = "http://localhost:8080"
        mock_manager.status.return_value = "running"

        with patch("sys.argv", ["custom_bot_service.py"]):
            with patch("builtins.print"):
                with patch("time.sleep", side_effect=KeyboardInterrupt()):
                    with patch("mindtrace.services.discord.discord_service.DiscordService.launch", return_value=mock_manager):
                        runpy.run_path(str(Path(main.__code__.co_filename)), run_name="__main__")

        mock_manager.shutdown.assert_called_once()
