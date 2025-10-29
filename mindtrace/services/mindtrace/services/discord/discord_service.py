"""Discord Service implementation for Mindtrace services.

This module provides a Service wrapper around DiscordClient that enables HTTP API endpoints and MCP integration while
maintaining the Discord bot functionality.
"""

import asyncio
import logging
from typing import Any, Optional
from unittest.mock import AsyncMock, Mock

import discord
from urllib3.util.url import Url

from mindtrace.services import Service
from mindtrace.services.discord.discord_client import DiscordClient
from mindtrace.services.discord.types import (
    DiscordCommandInput,
    DiscordCommandOutput,
    DiscordCommandSchema,
    DiscordCommandsOutput,
    DiscordCommandsSchema,
    DiscordStatusOutput,
    DiscordStatusSchema,
)


class DiscordService(Service):
    """Service wrapper for DiscordClient.

    This class provides:
    - HTTP API endpoints for Discord bot control
    - MCP tool integration
    - Service lifecycle management
    - Integration with Mindtrace infrastructure
    """

    def __init__(self, *, token: str | None = None, intents: Optional[Any] = None, **kwargs):
        """Initialize the Discord service.

        Args:
            token: Discord bot token (optional, will use config if not provided)
            intents: Discord intents configuration
            **kwargs: Additional arguments passed to Service
        """
        super().__init__(
            summary="Discord Bot Service",
            description="A Discord bot service with HTTP API endpoints and MCP integration",
            **kwargs,
        )

        # Create the Discord client
        self.discord_client = DiscordClient(token=token, intents=intents)

        # Bot task for running in background
        self._bot_task: Optional[asyncio.Task] = None

        # Add Discord-specific endpoints
        self._add_discord_endpoints()

        # Override the FastAPI lifespan to include Discord bot startup
        self._setup_lifespan()

    def _setup_lifespan(self):
        """Setup custom lifespan for Discord bot integration."""
        from contextlib import asynccontextmanager

        from fastapi import FastAPI

        @asynccontextmanager
        async def discord_lifespan(app: FastAPI):
            """Custom lifespan that includes Discord bot startup."""
            # Start Discord bot
            await self.startup()
            yield
            # Shutdown is handled by shutdown_cleanup()

        # Replace the app's lifespan
        self.app.router.lifespan_context = discord_lifespan

    def _add_discord_endpoints(self):
        """Add Discord-specific endpoints to the service."""

        # Add command execution endpoint
        self.add_endpoint(
            path="discord.execute",
            func=self.execute_command,
            schema=DiscordCommandSchema(),
            autolog_kwargs={"log_level": logging.INFO},
        )

        # Add bot status endpoint
        self.add_endpoint(path="discord.status", func=self.get_bot_status, schema=DiscordStatusSchema())

        # Add command list endpoint
        self.add_endpoint(path="discord.commands", func=self.get_commands, schema=DiscordCommandsSchema())

    async def startup(self):
        """Startup the Discord bot during service initialization."""
        if self._bot_task is not None:
            return  # Already started

        # Start bot in background task
        self._bot_task = asyncio.create_task(self._run_bot())

        self.logger.info("Discord bot startup initiated")

    async def _run_bot(self):
        """Run the Discord bot in a background task."""
        try:
            await self.discord_client.start_bot()
        except Exception as e:
            self.logger.error(f"Discord bot task failed: {e}")
            raise

    async def execute_command(self, payload: DiscordCommandInput) -> DiscordCommandOutput:
        """Execute a command via the service API.

        This method allows executing Discord slash commands programmatically through the FastAPI endpoint, useful for
        exposing AI models and other functionality through both Discord and HTTP interfaces.

        Args:
            payload: Command input data

        Returns:
            Command output
        """
        if self.discord_client.bot is None:
            return DiscordCommandOutput(
                response="Bot is not connected. Cannot execute commands.", embed=None, delete_after=None
            )

        # Parse the command from content
        command_name = payload.content.strip().split()[0].lstrip("/")

        # Find the command in the bot's command tree
        command = None
        for cmd in self.discord_client.bot.tree.get_commands():
            if cmd.name == command_name:
                command = cmd
                break

        if command is None:
            available_commands = [cmd.name for cmd in self.discord_client.bot.tree.get_commands()]
            return DiscordCommandOutput(
                response=f"Command '/{command_name}' not found. Available commands: {', '.join(available_commands)}",
                embed=None,
                delete_after=None,
            )

        # Set defaults and log warnings for missing required values
        defaults = self._get_default_values(payload, command_name)

        # Parse parameters from content string
        parsed_params = self._parse_command_parameters(payload.content, command)

        # Validate required parameters
        self._validate_required_parameters(parsed_params, command)

        # Create a minimal interaction for command execution
        mock_interaction = self._create_minimal_interaction(defaults)

        try:
            # Execute the command with parsed parameters
            await command.callback(mock_interaction, **parsed_params)

            # Get the response from the mock
            if mock_interaction.response.send_message.called:
                response = mock_interaction.response.send_message.call_args[0][0]
            elif mock_interaction.followup.send.called:
                response = mock_interaction.followup.send.call_args[0][0]
            else:
                response = "Command executed successfully"

            return DiscordCommandOutput(response=response, embed=None, delete_after=None)

        except Exception as e:
            self.logger.error(f"Error executing command '{command_name}': {e}")
            return DiscordCommandOutput(response=f"Error executing command: {str(e)}", embed=None, delete_after=None)

    def _get_default_values(self, payload: DiscordCommandInput, command_name: str) -> DiscordCommandInput:
        """Get default values for missing parameters and log warnings.

        Args:
            payload: Original command input
            command_name: Name of the command being executed

        Returns:
            Command input with defaults filled in
        """
        # Set reasonable defaults
        defaults = DiscordCommandInput(
            content=payload.content,
            author_id=payload.author_id or 0,
            channel_id=payload.channel_id or 0,
            guild_id=payload.guild_id,
            message_id=payload.message_id or 0,
        )

        # Log warnings for missing values that might be required
        if payload.author_id is None:
            self.logger.warning(f"author_id not provided for command '{command_name}'. Some commands may require this.")

        if payload.channel_id is None:
            self.logger.warning(
                f"channel_id not provided for command '{command_name}'. Some commands may require this."
            )

        if payload.message_id is None:
            self.logger.warning(
                f"message_id not provided for command '{command_name}'. Some commands may require this."
            )

        # Guild-specific commands might need guild_id
        guild_required_commands = ["info", "cleanup"]  # Commands that typically need guild context
        if command_name in guild_required_commands and payload.guild_id is None:
            self.logger.warning(
                f"guild_id not provided for command '{command_name}'. This command may require guild context."
            )

        return defaults

    def _parse_command_parameters(self, content: str, command) -> dict:
        """Parse parameters from command content string.

        Args:
            content: Command content string (e.g., "/roll 20")
            command: The Discord command object

        Returns:
            Dictionary of parsed parameters
        """
        # Split the content into parts
        parts = content.strip().split()
        if not parts:
            return {}

        # Remove the command name (first part)
        param_parts = parts[1:] if len(parts) > 1 else []

        # Get command parameters
        params = {}
        for param in command.parameters:
            param_name = param.name
            param_type = param.type

            # Convert Discord parameter type to Python type
            python_type = self._get_python_type_from_discord_type(param_type)

            # Try to find the parameter value in the remaining parts
            if param_parts:
                try:
                    # Convert the first parameter to the expected type
                    value = python_type(param_parts[0])
                    params[param_name] = value
                    # Remove the used parameter
                    param_parts = param_parts[1:]
                except (ValueError, IndexError, TypeError):
                    # If conversion fails or no more parts, use default
                    if hasattr(param, "default") and param.default is not None:
                        params[param_name] = param.default
                    else:
                        params[param_name] = None
            else:
                # No more parts, use default
                if hasattr(param, "default") and param.default is not None:
                    params[param_name] = param.default
                else:
                    params[param_name] = None

        return params

    def _validate_required_parameters(self, parsed_params: dict, command) -> None:
        """Validate that all required parameters are provided.

        Args:
            parsed_params: Dictionary of parsed parameters
            command: The Discord command object

        Raises:
            ValueError: If required parameters are missing
        """
        for param in command.parameters:
            param_name = param.name
            if param_name not in parsed_params or parsed_params[param_name] is None:
                # Check if this parameter has a default value
                if not (hasattr(param, "default") and param.default is not None):
                    raise ValueError(f"Required parameter '{param_name}' is missing for command '{command.name}'")

    def _get_python_type_from_discord_type(self, discord_type) -> type:
        """Convert Discord parameter type to Python type.

        Args:
            discord_type: Discord parameter type enum

        Returns:
            Python type
        """
        # Map Discord parameter types to Python types
        type_mapping = {
            discord.AppCommandOptionType.string: str,
            discord.AppCommandOptionType.integer: int,
            discord.AppCommandOptionType.number: float,
            discord.AppCommandOptionType.boolean: bool,
            discord.AppCommandOptionType.user: int,  # User ID
            discord.AppCommandOptionType.channel: int,  # Channel ID
            discord.AppCommandOptionType.role: int,  # Role ID
            discord.AppCommandOptionType.mentionable: int,  # ID
            discord.AppCommandOptionType.attachment: str,  # Attachment URL
        }

        return type_mapping.get(discord_type, str)  # Default to str if unknown

    def _create_minimal_interaction(self, payload: DiscordCommandInput) -> Mock:
        """Create a minimal mock Discord interaction for command execution.

        This creates only the essential attributes needed for command execution
        without generating fake Discord server data. The focus is on exposing
        the same functionality through both Discord and HTTP interfaces.

        Args:
            payload: Command input data

        Returns:
            Minimal mock interaction object
        """
        # Create minimal mock user
        mock_user = Mock()
        mock_user.id = payload.author_id
        mock_user.mention = f"<@{payload.author_id}>" if payload.author_id else "<@0>"
        mock_user.display_name = f"User{payload.author_id}" if payload.author_id else "API User"

        # Create minimal mock guild if guild_id is provided (for guild-specific commands)
        mock_guild = None
        if payload.guild_id:
            mock_guild = Mock()
            mock_guild.id = payload.guild_id
            # Don't populate fake data - let commands handle missing data gracefully
            mock_guild.get_member = Mock(return_value=mock_user)

        # Create minimal mock channel
        mock_channel = Mock()
        mock_channel.id = payload.channel_id

        # Create minimal mock interaction
        mock_interaction = Mock()
        mock_interaction.user = mock_user
        mock_interaction.guild = mock_guild
        mock_interaction.channel = mock_channel
        mock_interaction.message_id = payload.message_id

        # Create mock response
        mock_response = Mock()
        mock_response.send_message = AsyncMock()
        mock_response.defer = AsyncMock()
        mock_interaction.response = mock_response

        # Create mock followup
        mock_followup = Mock()
        mock_followup.send = AsyncMock()
        mock_interaction.followup = mock_followup

        return mock_interaction

    def get_bot_status(self) -> DiscordStatusOutput:
        """Get the current bot status.

        Returns:
            Bot status information
        """
        if self.discord_client.bot is None or self.discord_client.bot.user is None:
            return DiscordStatusOutput(bot_name=None, guild_count=0, user_count=0, latency=0.0, status="not_started")

        return DiscordStatusOutput(
            bot_name=self.discord_client.bot.user.name,
            guild_count=len(self.discord_client.bot.guilds),
            user_count=len(self.discord_client.bot.users),
            latency=0.0
            if self.discord_client.bot.latency is None or str(self.discord_client.bot.latency) == "nan"
            else self.discord_client.bot.latency,
            status=str(self.discord_client.bot.status),
        )

    def get_commands(self) -> DiscordCommandsOutput:
        """Get list of registered commands.

        Returns:
            Command information
        """
        return DiscordCommandsOutput(
            commands=[
                {
                    "name": cmd.name,
                    "description": cmd.description,
                    "usage": cmd.usage,
                    "aliases": cmd.aliases,
                    "category": cmd.category,
                    "enabled": cmd.enabled,
                    "hidden": cmd.hidden,
                }
                for cmd in self.discord_client._commands.values()
            ]
        )

    # Delegate Discord client methods
    def register_command(self, *args, **kwargs):
        """Register a command with the Discord client."""
        return self.discord_client.register_command(*args, **kwargs)

    def register_event_handler(self, *args, **kwargs):
        """Register an event handler with the Discord client."""
        return self.discord_client.register_event_handler(*args, **kwargs)

    @classmethod
    def launch(
        cls,
        *,
        url: str | Url | None = None,
        host: str | None = None,
        port: int | None = None,
        block: bool = False,
        num_workers: int = 1,
        wait_for_launch: bool = True,
        timeout: int = 60,
        progress_bar: bool = True,
        **kwargs,
    ):
        """Launch a Discord service and wait for the Discord bot to be ready.

        This overrides the base Service.launch() method to ensure the Discord bot
        is fully connected before returning the connection manager.

        Args:
            url: Full URL string or Url object (highest priority)
            host: Host address (used if url not provided)
            port: Port number (used if url not provided)
            block: If True, blocks the calling process and keeps the server running
            num_workers: Number of worker processes
            wait_for_launch: Whether to wait for server startup
            timeout: Timeout for server startup in seconds
            progress_bar: Show progress bar during startup
            **kwargs: Additional parameters passed to the server's __init__ method
        """
        # First, launch the service using the parent method
        connection_manager = super().launch(
            url=url,
            host=host,
            port=port,
            block=block,
            num_workers=num_workers,
            wait_for_launch=wait_for_launch,
            timeout=timeout,
            progress_bar=progress_bar,
            **kwargs,
        )

        # If we're not waiting for launch, return immediately
        if not wait_for_launch:
            return connection_manager

        # Wait for Discord bot to be ready
        import time

        from mindtrace.core import Timeout

        # Give the bot a moment to start the connection process
        time.sleep(2)

        def check_discord_ready():
            """Check if Discord bot is ready."""
            try:
                import requests

                response = requests.post(f"{connection_manager.url}/discord.status", json={})
                if response.status_code == 200:
                    data = response.json()
                    # Bot is ready if it has a name and is not in "not_started" status
                    return data.get("bot_name") is not None and data.get("status") != "not_started"
                return False
            except Exception:
                return False

        # Wait for Discord bot to be ready with a separate timeout
        discord_timeout = Timeout(
            timeout=min(timeout, 30),
            exceptions=(),
            progress_bar=progress_bar,
            desc="Waiting for Discord bot to connect",
        )

        try:
            discord_timeout.run(check_discord_ready)
            cls.logger.info("Discord bot is ready and connected")
        except Exception as e:
            cls.logger.warning(f"Discord bot may not be fully connected: {e}")
            # Don't fail the launch, just warn - the service is still functional

        return connection_manager

    async def shutdown_cleanup(self):
        """Cleanup when shutting down the service."""
        await super().shutdown_cleanup()

        # Stop the Discord bot
        if self._bot_task is not None:
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass

        if self.discord_client.bot is not None:
            try:
                await self.discord_client.stop_bot()
            except Exception as e:
                self.logger.error(f"Failed to stop Discord bot: {e}")

        self.logger.info("Discord bot shutdown completed")
