"""Discord Service implementation for Mindtrace services.

This module provides a Service wrapper around BaseDiscordClient that enables
HTTP API endpoints and MCP integration while maintaining the Discord bot functionality.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from mindtrace.services import Service
from mindtrace.services.discord.discord_client import DiscordClient
from mindtrace.services.discord.types import (
    DiscordCommandInput,
    DiscordCommandOutput,
    DiscordCommandSchema,
    DiscordCommandsInput,
    DiscordCommandsOutput,
    DiscordCommandsSchema,
    DiscordStatusInput,
    DiscordStatusOutput,
    DiscordStatusSchema
)


class DiscordService(Service):
    """Service wrapper for DiscordClient.
    
    This class provides:
    - HTTP API endpoints for Discord bot control
    - MCP tool integration
    - Service lifecycle management
    - Integration with Mindtrace infrastructure
    """
    
    def __init__(
        self,
        *,
        token: str | None = None,
        intents: Optional[Any] = None,
        **kwargs
    ):
        """Initialize the Discord service.
        
        Args:
            token: Discord bot token (optional, will use config if not provided)
            intents: Discord intents configuration
            **kwargs: Additional arguments passed to Service
        """
        super().__init__(
            summary="Discord Bot Service",
            description="A Discord bot service with HTTP API endpoints and MCP integration",
            **kwargs
        )
        
        # Create the Discord client
        self.discord_client = DiscordClient(
            token=token,
            intents=intents
        )
        
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
            autolog_kwargs={"log_level": logging.INFO}
        )
        
        # Add bot status endpoint
        self.add_endpoint(
            path="discord.status",
            func=self.get_bot_status,
            schema=DiscordStatusSchema()
        )
        
        # Add command list endpoint
        self.add_endpoint(
            path="discord.commands",
            func=self.get_commands,
            schema=DiscordCommandsSchema()
        )
    
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
        
        Args:
            payload: Command input data
            
        Returns:
            Command output
        """
        # This would need to be implemented to execute commands programmatically
        # For now, return a placeholder response
        return DiscordCommandOutput(
            response=f"Command '{payload.content}' received from user {payload.author_id}"
        )
    
    def get_bot_status(self, payload: None = None) -> DiscordStatusOutput:
        """Get the current bot status.
        
        Returns:
            Bot status information
        """
        if self.discord_client.bot is None:
            return DiscordStatusOutput(
                bot_name=None,
                guild_count=0,
                user_count=0,
                latency=0.0,
                status="not_started"
            )
        
        return DiscordStatusOutput(
            bot_name=self.discord_client.bot.user.name if self.discord_client.bot.user else None,
            guild_count=len(self.discord_client.bot.guilds),
            user_count=len(self.discord_client.bot.users),
            latency=0.0 if self.discord_client.bot.latency is None or str(self.discord_client.bot.latency) == 'nan' else self.discord_client.bot.latency,
            status=str(self.discord_client.bot.status)
        )
    
    def get_commands(self, payload: None = None) -> DiscordCommandsOutput:
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
                    "hidden": cmd.hidden
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
