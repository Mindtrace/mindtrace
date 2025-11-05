"""Discord client implementation for Mindtrace services.

This module provides a base Discord client that can be extended for different bot implementations.
It follows the Mindtrace Service patterns and provides a clean interface for command registration.
"""

from typing import Any, Callable, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from mindtrace.core import Mindtrace, ifnone
from mindtrace.services.discord.types import DiscordCommand, DiscordEventHandler, DiscordEventType


class DiscordClient(Mindtrace):
    """Discord client that can be extended for different bot implementations.

    This class provides:
    - Command registration and management
    - Event handling system
    - Integration with Mindtrace patterns
    - Configurable bot behavior
    """

    def __init__(self, *, token: str | None = None, intents: Optional[discord.Intents] = None, **kwargs):
        """Initialize the Discord client.

        Args:
            token: Discord bot token (optional, will use config if not provided)
            intents: Discord intents configuration
            **kwargs: Additional arguments passed to Mindtrace
        """
        super().__init__(**kwargs)

        # Discord bot configuration
        default_token = self.config.get_secret("MINDTRACE_API_KEYS", "DISCORD")
        self.token = ifnone(token, default=default_token)
        if self.token is None:
            raise RuntimeError(
                "No Discord token provided. Pass in a token or provide a MINDTRACE_API_KEYS__DISCORD in the Mindtrace config."
            )
        self.intents = intents or discord.Intents.default()
        self.intents.message_content = True

        # Bot instance
        self.bot = commands.Bot(
            intents=self.intents,
            command_prefix="!",  # Unused but required by discord.py
            help_command=None,  # We'll implement custom help
        )

        # The bot already has a command tree by default, no need to create a new one

        # Command and event storage
        self._commands: Dict[str, DiscordCommand] = {}
        self._event_handlers: Dict[DiscordEventType, List[DiscordEventHandler]] = {}
        self._command_handlers: Dict[str, Callable] = {}

        # Setup bot events
        self._setup_bot_events()

    def _setup_bot_events(self):
        """Setup Discord bot event handlers."""

        @self.bot.event
        async def on_ready():
            """Called when the bot is ready."""
            self.logger.info(f"Discord bot {self.bot.user} is ready!")
            self.logger.info(f"Connected to {len(self.bot.guilds)} guilds")

            # Sync slash commands
            try:
                print(f"Syncing {len(self.bot.tree.get_commands())} commands...")
                synced = await self.bot.tree.sync()
                print(f"Successfully synced {len(synced)} command(s)")
                self.logger.info(f"Synced {len(synced)} command(s)")
            except Exception as e:
                print(f"Failed to sync commands: {e}")
                self.logger.error(f"Failed to sync commands: {e}")

            # Set bot status
            await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="/help"))

        @self.bot.event
        async def on_message(message: discord.Message):
            """Handle incoming messages."""
            # Ignore messages from bots (including self)
            if message.author.bot:
                return

            # Process commands first
            await self.bot.process_commands(message)

            # Handle custom events
            await self._handle_event(DiscordEventType.MESSAGE, message=message)

        @self.bot.event
        async def on_reaction_add(reaction: discord.Reaction, user: discord.Member):
            """Handle reaction events."""
            if user.bot:
                return

            await self._handle_event(DiscordEventType.REACTION, reaction=reaction, user=user, action="add")

        @self.bot.event
        async def on_member_join(member: discord.Member):
            """Handle member join events."""
            await self._handle_event(DiscordEventType.MEMBER_JOIN, member=member)

        @self.bot.event
        async def on_member_remove(member: discord.Member):
            """Handle member leave events."""
            await self._handle_event(DiscordEventType.MEMBER_LEAVE, member=member)

        @self.bot.event
        async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
            """Handle voice state changes."""
            await self._handle_event(DiscordEventType.VOICE_STATE_UPDATE, member=member, before=before, after=after)

    def register_command(
        self,
        name: str,
        description: str,
        usage: str,
        handler: Callable,
        aliases: Optional[List[str]] = None,
        category: str = "General",
        enabled: bool = True,
        hidden: bool = False,
        cooldown: Optional[int] = None,
        permissions: Optional[List[str]] = None,
        parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        """Register a new slash command with the bot.

        Args:
            name: Command name
            description: Command description
            usage: Usage instructions (for documentation)
            handler: Function to handle the command
            aliases: Alternative command names (not used in slash commands)
            category: Command category
            enabled: Whether the command is enabled
            hidden: Whether to hide from help
            cooldown: Cooldown in seconds
            permissions: Required permissions
            parameters: Dictionary of parameter descriptions for slash commands
        """
        command = DiscordCommand(
            name=name,
            description=description,
            usage=usage,
            aliases=aliases or [],
            category=category,
            enabled=enabled,
            hidden=hidden,
            cooldown=cooldown,
            permissions=permissions,
        )

        self._commands[name] = command
        self._command_handlers[name] = handler

        # Create slash command
        @self.bot.tree.command(name=name, description=description)
        async def slash_command_wrapper(interaction: discord.Interaction, *args):
            await self._execute_slash_command(interaction, name, *args)

        # Add parameter descriptions if provided
        if parameters:
            for param_name, param_info in parameters.items():
                app_commands.describe(**{param_name: param_info.get("description", "")})

        self.logger.info(f"Registered slash command: /{name}")

    def register_event_handler(self, event_type: DiscordEventType, handler: DiscordEventHandler):
        """Register an event handler.

        Args:
            event_type: Type of event to handle
            handler: Event handler instance
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []

        self._event_handlers[event_type].append(handler)
        self.logger.info(f"Registered event handler for {event_type.value}")

    async def _execute_slash_command(self, interaction: discord.Interaction, command_name: str, *args):
        """Execute a registered slash command.

        Args:
            interaction: Discord interaction
            command_name: Name of the command to execute
            *args: Command arguments
        """
        if command_name not in self._commands:
            await interaction.response.send_message(f"Unknown command: {command_name}", ephemeral=True)
            return

        command = self._commands[command_name]

        # Check if command is enabled
        if not command.enabled:
            await interaction.response.send_message("This command is currently disabled.", ephemeral=True)
            return

        # Check permissions
        if command.permissions and interaction.guild:
            member = interaction.guild.get_member(interaction.user.id)
            if member:
                for permission in command.permissions:
                    if not getattr(member.guild_permissions, permission, False):
                        await interaction.response.send_message(
                            f"You need the `{permission}` permission to use this command.", ephemeral=True
                        )
                        return

        # Check cooldown
        if command.cooldown:
            # Simple cooldown implementation - could be enhanced with proper cooldown tracking
            pass

        try:
            # Defer the response to avoid timeout
            await interaction.response.defer()

            # Call the command handler
            handler = self._command_handlers[command_name]
            result = await handler(interaction, *args)

            if result:
                await interaction.followup.send(result)

        except Exception as e:
            self.logger.error(f"Error executing slash command {command_name}: {e}")
            await interaction.followup.send(f"An error occurred while executing the command: {str(e)}", ephemeral=True)

    async def _execute_command(self, ctx: commands.Context, command_name: str, *args):
        """Execute a registered command (legacy prefix command support).

        Args:
            ctx: Discord context
            command_name: Name of the command to execute
            *args: Command arguments
        """
        if command_name not in self._commands:
            await ctx.send(f"Unknown command: {command_name}")
            return

        command = self._commands[command_name]

        # Check if command is enabled
        if not command.enabled:
            await ctx.send("This command is currently disabled.")
            return

        # Check permissions
        if command.permissions:
            for permission in command.permissions:
                if not getattr(ctx.author.guild_permissions, permission, False):
                    await ctx.send(f"You need the `{permission}` permission to use this command.")
                    return

        # Check cooldown
        if command.cooldown:
            # Simple cooldown implementation - could be enhanced with proper cooldown tracking
            pass

        try:
            # Call the command handler
            handler = self._command_handlers[command_name]
            result = await handler(ctx, *args)

            if result:
                await ctx.send(result)

        except Exception as e:
            self.logger.error(f"Error executing command {command_name}: {e}")
            await ctx.send(f"An error occurred while executing the command: {str(e)}")

    async def _handle_event(self, event_type: DiscordEventType, **kwargs):
        """Handle Discord events by calling registered handlers.

        Args:
            event_type: Type of event
            **kwargs: Event-specific data
        """
        if event_type in self._event_handlers:
            for handler in self._event_handlers[event_type]:
                try:
                    await handler.handle(event_type, **kwargs)
                except Exception as e:
                    self.logger.error(f"Error in event handler for {event_type.value}: {e}")

    async def start_bot(self):
        """Start the Discord bot."""
        try:
            await self.bot.start(self.token)
        except Exception as e:
            self.logger.error(f"Failed to start Discord bot: {e}")
            raise

    async def stop_bot(self):
        """Stop the Discord bot."""
        try:
            await self.bot.close()
        except Exception as e:
            self.logger.error(f"Failed to stop Discord bot: {e}")
            raise
