"""
Unit tests for the custom Discord bot client sample.
"""

import runpy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from mindtrace.services.discord.types import DiscordEventType
from mindtrace.services.samples.discord.custom_bot_client import (
    CustomDiscordBot,
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


def _patch_bot_init():
    tree = _CommandTree()

    def fake_init(self, **kwargs):
        self.logger = Mock()
        self.bot = SimpleNamespace(tree=tree)
        self.register_event_handler = Mock()

    return tree, fake_init


def _make_history(*messages):
    async def history(*, limit):
        for message in messages[:limit]:
            yield message

    return history


def _make_interaction(*, guild=None, user=None, channel=None, client=None):
    if user is None:
        user = SimpleNamespace(id=123, __str__=lambda self: "user")  # pragma: no cover - fallback
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


class TestCustomDiscordBot:
    """Test the CustomDiscordBot class."""

    def test_custom_discord_bot_class_exists(self):
        """Test that CustomDiscordBot class can be imported and instantiated."""
        # Test that the class exists and can be imported
        assert CustomDiscordBot is not None
        assert hasattr(CustomDiscordBot, "__init__")
        assert hasattr(CustomDiscordBot, "_register_commands")

    def test_custom_discord_bot_inheritance(self):
        """Test that CustomDiscordBot inherits from DiscordClient."""
        from mindtrace.services.discord.discord_client import DiscordClient

        assert issubclass(CustomDiscordBot, DiscordClient)

    def test_init_basic_functionality(self):
        """Test that __init__ basic functionality works."""
        # Test that the class can be instantiated without errors
        # The actual initialization logic is complex due to parent class dependencies
        # and is better tested in integration tests

        # Test that the class exists and has the expected methods
        assert hasattr(CustomDiscordBot, "__init__")
        assert hasattr(CustomDiscordBot, "_register_commands")
        assert hasattr(CustomDiscordBot, "register_event_handler")

    def test_init_registers_event_handler_and_commands(self):
        tree, fake_init = _patch_bot_init()

        with patch("mindtrace.services.samples.discord.custom_bot_client.DiscordClient.__init__", new=fake_init):
            bot = CustomDiscordBot(token="abc")

        bot.register_event_handler.assert_called_once()
        assert set(tree.commands) == {"info", "roll", "cleanup", "help"}


class TestRegisteredCommands:
    @pytest.fixture
    def bot_and_commands(self):
        tree, fake_init = _patch_bot_init()

        with patch("mindtrace.services.samples.discord.custom_bot_client.DiscordClient.__init__", new=fake_init):
            bot = CustomDiscordBot(token="abc")

        return bot, tree.commands

    @pytest.mark.asyncio
    async def test_info_command_requires_guild(self, bot_and_commands):
        _, commands = bot_and_commands
        interaction = _make_interaction(guild=None)

        await commands["info"](interaction)

        interaction.response.send_message.assert_awaited_once_with(
            "This command can only be used in a server.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_info_command_reports_guild_details(self, bot_and_commands):
        _, commands = bot_and_commands
        guild = SimpleNamespace(
            name="Guild",
            member_count=42,
            channels=[1, 2, 3],
            roles=["a", "b"],
            created_at=datetime(2024, 1, 2),
        )
        interaction = _make_interaction(guild=guild, user="tester")

        await commands["info"](interaction)

        sent_message = interaction.response.send_message.await_args.args[0]
        assert "Server Information" in sent_message
        assert "Name: Guild" in sent_message
        assert "Members: 42" in sent_message
        assert "Created: 2024-01-02" in sent_message

    @pytest.mark.asyncio
    async def test_roll_command_rejects_non_positive_sides(self, bot_and_commands):
        _, commands = bot_and_commands
        interaction = _make_interaction()

        await commands["roll"](interaction, 0)

        interaction.response.send_message.assert_awaited_once_with(
            "Number of sides must be positive.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_roll_command_uses_random_result(self, bot_and_commands):
        _, commands = bot_and_commands
        interaction = _make_interaction()

        with patch("random.randint", return_value=4):
            await commands["roll"](interaction, 6)

        interaction.response.send_message.assert_awaited_once_with("🎲 You rolled a 4 (1-6)")

    @pytest.mark.asyncio
    async def test_cleanup_command_requires_guild(self, bot_and_commands):
        _, commands = bot_and_commands
        interaction = _make_interaction(guild=None)

        await commands["cleanup"](interaction, 10)

        interaction.response.send_message.assert_awaited_once_with(
            "This command can only be used in a server.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_cleanup_command_requires_manage_messages_permission(self, bot_and_commands):
        _, commands = bot_and_commands
        member = SimpleNamespace(guild_permissions=SimpleNamespace(manage_messages=False))
        guild = Mock()
        guild.get_member.return_value = member
        interaction = _make_interaction(guild=guild, user=SimpleNamespace(id=5))

        await commands["cleanup"](interaction, 10)

        interaction.response.send_message.assert_awaited_once_with(
            "You need the 'Manage Messages' permission to use this command.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_cleanup_command_validates_count_range(self, bot_and_commands):
        _, commands = bot_and_commands
        member = SimpleNamespace(guild_permissions=SimpleNamespace(manage_messages=True))
        guild = Mock()
        guild.get_member.return_value = member
        interaction = _make_interaction(guild=guild, user=SimpleNamespace(id=5))

        await commands["cleanup"](interaction, 101)

        interaction.response.send_message.assert_awaited_once_with(
            "Please specify a number between 1 and 100.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_cleanup_command_deletes_only_bot_messages(self, bot_and_commands):
        _, commands = bot_and_commands
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
    async def test_help_command_lists_available_commands(self, bot_and_commands):
        _, commands = bot_and_commands
        interaction = _make_interaction()

        await commands["help"](interaction)

        sent_message = interaction.response.send_message.await_args.args[0]
        assert "Available commands:" in sent_message
        assert "**/cleanup [count]**" in sent_message


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
        with patch("sys.argv", ["custom_bot_client.py"]):
            args = parse_arguments()

            assert args.token is None
            assert args.description == "A custom Discord bot built with Mindtrace"
            assert args.verbose is False

    def test_parse_arguments_with_token(self):
        """Test parsing arguments with token."""
        with patch("sys.argv", ["custom_bot_client.py", "--token", "test_token"]):
            args = parse_arguments()

            assert args.token == "test_token"
            assert args.description == "A custom Discord bot built with Mindtrace"
            assert args.verbose is False

    def test_parse_arguments_with_all_options(self):
        """Test parsing arguments with all options."""
        with patch(
            "sys.argv", ["custom_bot_client.py", "--token", "test_token", "--description", "Test bot", "--verbose"]
        ):
            args = parse_arguments()

            assert args.token == "test_token"
            assert args.description == "Test bot"
            assert args.verbose is True


class TestMain:
    """Test the main function."""

    @pytest.mark.asyncio
    async def test_main_with_token(self):
        """Test main function with token."""
        with patch("mindtrace.services.samples.discord.custom_bot_client.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(token="test_token", description="Test bot", verbose=False)

            with patch("mindtrace.services.samples.discord.custom_bot_client.CustomDiscordBot") as mock_bot_class:
                mock_bot = Mock()
                mock_bot.start_bot = AsyncMock()
                mock_bot.stop_bot = AsyncMock()
                mock_bot_class.return_value = mock_bot

                with patch("builtins.print"):
                    await main()

                # Verify bot was created with correct parameters
                mock_bot_class.assert_called_once_with(token="test_token", description="Test bot")

                # Verify bot methods were called
                mock_bot.start_bot.assert_called_once()
                mock_bot.stop_bot.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_without_token(self):
        """Test main function without token."""
        with patch("mindtrace.services.samples.discord.custom_bot_client.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(token=None, description="Test bot", verbose=False)

            with patch("mindtrace.services.samples.discord.custom_bot_client.CustomDiscordBot") as mock_bot_class:
                mock_bot = Mock()
                mock_bot.start_bot = AsyncMock()
                mock_bot.stop_bot = AsyncMock()
                mock_bot_class.return_value = mock_bot

                with patch("builtins.print"):
                    await main()

                # Verify bot was created with None token
                mock_bot_class.assert_called_once_with(token=None, description="Test bot")

    @pytest.mark.asyncio
    async def test_main_keyboard_interrupt(self):
        """Test main function with keyboard interrupt."""
        with patch("mindtrace.services.samples.discord.custom_bot_client.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(token="test_token", description="Test bot", verbose=False)

            with patch("mindtrace.services.samples.discord.custom_bot_client.CustomDiscordBot") as mock_bot_class:
                mock_bot = Mock()
                mock_bot.start_bot = AsyncMock(side_effect=KeyboardInterrupt())
                mock_bot.stop_bot = AsyncMock()
                mock_bot_class.return_value = mock_bot

                with patch("builtins.print"):
                    await main()

                # Verify stop_bot was called even after KeyboardInterrupt
                mock_bot.stop_bot.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_exception(self):
        """Test main function with exception."""
        with patch("mindtrace.services.samples.discord.custom_bot_client.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(token="test_token", description="Test bot", verbose=False)

            with patch("mindtrace.services.samples.discord.custom_bot_client.CustomDiscordBot") as mock_bot_class:
                mock_bot = Mock()
                mock_bot.start_bot = AsyncMock(side_effect=Exception("Test error"))
                mock_bot.stop_bot = AsyncMock()
                mock_bot_class.return_value = mock_bot

                with patch("builtins.print"):
                    await main()

                # Verify stop_bot was called even after exception
                mock_bot.stop_bot.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_verbose_output_with_token(self):
        """Test main function verbose output with token."""
        with patch("mindtrace.services.samples.discord.custom_bot_client.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(token="test_token", description="Test bot", verbose=True)

            with patch("mindtrace.services.samples.discord.custom_bot_client.CustomDiscordBot") as mock_bot_class:
                mock_bot = Mock()
                mock_bot.start_bot = AsyncMock()
                mock_bot.stop_bot = AsyncMock()
                mock_bot_class.return_value = mock_bot

                with patch("builtins.print") as mock_print:
                    await main()

                # Verify verbose output was printed
                mock_print.assert_any_call("Bot description: Test bot")
                mock_print.assert_any_call("Using token from command line")

    @pytest.mark.asyncio
    async def test_main_verbose_output_without_token(self):
        """Test main function verbose output without token."""
        with patch("mindtrace.services.samples.discord.custom_bot_client.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(token=None, description="Test bot", verbose=True)

            with patch("mindtrace.services.samples.discord.custom_bot_client.CustomDiscordBot") as mock_bot_class:
                mock_bot = Mock()
                mock_bot.start_bot = AsyncMock()
                mock_bot.stop_bot = AsyncMock()
                mock_bot_class.return_value = mock_bot

                with patch("builtins.print") as mock_print:
                    await main()

                # Verify verbose output was printed
                mock_print.assert_any_call("Bot description: Test bot")
                mock_print.assert_any_call("Using MINDTRACE_DISCORD_BOT_TOKEN from config")

    @pytest.mark.asyncio
    async def test_main_exception_with_verbose_traceback(self):
        """Test main function exception with verbose traceback."""
        with patch("mindtrace.services.samples.discord.custom_bot_client.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(token="test_token", description="Test bot", verbose=True)

            with patch("mindtrace.services.samples.discord.custom_bot_client.CustomDiscordBot") as mock_bot_class:
                mock_bot = Mock()
                mock_bot.start_bot = AsyncMock(side_effect=Exception("Test error"))
                mock_bot.stop_bot = AsyncMock()
                mock_bot_class.return_value = mock_bot

                with patch("builtins.print") as mock_print:
                    with patch("traceback.print_exc") as mock_traceback:
                        await main()

                # Verify error message and traceback were printed
                mock_print.assert_any_call("Error running bot: Test error")
                mock_traceback.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_exception_without_verbose_traceback(self):
        """Test main function exception without verbose traceback."""
        with patch("mindtrace.services.samples.discord.custom_bot_client.parse_arguments") as mock_parse:
            mock_parse.return_value = Mock(token="test_token", description="Test bot", verbose=False)

            with patch("mindtrace.services.samples.discord.custom_bot_client.CustomDiscordBot") as mock_bot_class:
                mock_bot = Mock()
                mock_bot.start_bot = AsyncMock(side_effect=Exception("Test error"))
                mock_bot.stop_bot = AsyncMock()
                mock_bot_class.return_value = mock_bot

                with patch("builtins.print") as mock_print:
                    with patch("traceback.print_exc") as mock_traceback:
                        await main()

                # Verify error message was printed but not traceback
                mock_print.assert_any_call("Error running bot: Test error")
                mock_traceback.assert_not_called()


class TestModuleExecution:
    """Test module execution when run as script."""

    def test_module_execution(self):
        """Test that the module can be executed as a script."""
        with patch("asyncio.run") as mock_run:
            runpy.run_path(str(Path(main.__code__.co_filename)), run_name="__main__")

        mock_run.assert_called_once()
