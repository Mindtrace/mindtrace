#!/usr/bin/env python3
"""Examples demonstrating both DiscordClient and DiscordService usage patterns.

This file shows:
1. Direct usage of DiscordClient (simple Discord bot)
2. Service usage of DiscordService (Discord bot with HTTP API)
"""

import argparse
import asyncio
from typing import Optional

import discord

from mindtrace.services.discord import DiscordClient, DiscordEventHandler, DiscordEventType, DiscordService


class ExampleEventHandler(DiscordEventHandler):
    """Example event handler for demonstration."""

    async def handle(self, event_type: DiscordEventType, **kwargs):
        """Handle Discord events with custom logic."""
        if event_type == DiscordEventType.MESSAGE:
            message = kwargs.get("message")
            if message and "hello" in message.content.lower():
                await message.channel.send("Hello there! 👋")

        elif event_type == DiscordEventType.MEMBER_JOIN:
            member = kwargs.get("member")
            if member:
                # Send welcome message to the first available text channel
                for channel in member.guild.text_channels:
                    if channel.permissions_for(member.guild.me).send_messages:
                        await channel.send(f"Welcome {member.mention} to the server! 🎉")
                        break


class SimpleDiscordBot(DiscordClient):
    """Simple Discord bot using DiscordClient (Direct usage pattern)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Register event handlers
        self.register_event_handler(DiscordEventType.MESSAGE, ExampleEventHandler())

        # Register slash commands
        self._register_commands()

    def _register_commands(self):
        """Register slash commands."""

        @self.bot.tree.command(name="info", description="Get server information")
        async def info_command(interaction: discord.Interaction):
            """Get server information."""
            if not interaction.guild:
                await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
                return

            guild = interaction.guild
            response = (
                f"**Server Information**\n"
                f"Name: {guild.name}\n"
                f"Members: {guild.member_count}\n"
                f"Channels: {len(guild.channels)}\n"
                f"Roles: {len(guild.roles)}\n"
                f"Created: {guild.created_at.strftime('%Y-%m-%d')}"
            )
            await interaction.response.send_message(response)

        @self.bot.tree.command(name="ping", description="Check bot latency")
        async def ping_command(interaction: discord.Interaction):
            """Check bot latency."""
            latency = round(self.bot.latency * 1000)
            await interaction.response.send_message(f"🏓 Pong! Latency: {latency}ms")


class AdvancedDiscordService(DiscordService):
    """Advanced Discord service using DiscordService (Service pattern)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Register event handlers
        self.register_event_handler(DiscordEventType.MESSAGE, ExampleEventHandler())

        # Register slash commands
        self._register_commands()

    def _register_commands(self):
        """Register slash commands."""

        @self.discord_client.bot.tree.command(name="info", description="Get server information")
        async def info_command(interaction: discord.Interaction):
            """Get server information."""
            if not interaction.guild:
                await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
                return

            guild = interaction.guild
            response = (
                f"**Server Information**\n"
                f"Name: {guild.name}\n"
                f"Members: {guild.member_count}\n"
                f"Channels: {len(guild.channels)}\n"
                f"Roles: {len(guild.roles)}\n"
                f"Created: {guild.created_at.strftime('%Y-%m-%d')}\n"
                f"Service ID: {self.id}"
            )
            await interaction.response.send_message(response)

        @self.discord_client.bot.tree.command(name="ping", description="Check bot latency")
        async def ping_command(interaction: discord.Interaction):
            """Check bot latency."""
            latency = round(self.discord_client.bot.latency * 1000)
            await interaction.response.send_message(f"🏓 Pong! Latency: {latency}ms")

        @self.discord_client.bot.tree.command(name="status", description="Get service status")
        async def status_command(interaction: discord.Interaction):
            """Get service status."""
            status = self.get_bot_status(None)
            response = (
                f"**Service Status**\n"
                f"Bot: {status.bot_name or 'Not connected'}\n"
                f"Guilds: {status.guild_count}\n"
                f"Users: {status.user_count}\n"
                f"Latency: {status.latency:.2f}ms\n"
                f"Status: {status.status}"
            )
            await interaction.response.send_message(response)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run Discord bot examples",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run simple bot (DiscordClient)
  python usage_examples.py --mode simple
  
  # Run service bot (DiscordService)
  python usage_examples.py --mode service
  
  # Run service bot with custom port
  python usage_examples.py --mode service --port 8081
        """,
    )

    parser.add_argument(
        "--mode",
        choices=["simple", "service"],
        default="simple",
        help="Bot mode: 'simple' for DiscordClient, 'service' for DiscordService",
    )

    parser.add_argument("--token", type=str, default=None, help="Discord bot token (overrides config)")

    parser.add_argument("--port", type=int, default=8080, help="Port for service mode (default: 8080)")

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    return parser.parse_args()


async def run_simple_bot(token: Optional[str], verbose: bool):
    """Run the simple bot using DiscordClient."""
    print("Starting simple Discord bot (DiscordClient)...")

    bot = SimpleDiscordBot(token=token)

    try:
        print("Bot is starting...")
        await bot.start_bot()
    except KeyboardInterrupt:
        print("\nShutting down bot...")
    except Exception as e:
        print(f"Error running bot: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
    finally:
        await bot.stop_bot()


def run_service_bot(token: Optional[str], port: int, verbose: bool):
    """Run the service bot using DiscordService."""
    print(f"Starting Discord service (DiscordService) on port {port}...")

    # Launch the service
    service_manager = AdvancedDiscordService.launch(
        host="localhost", port=port, token=token, wait_for_launch=True, timeout=30
    )

    print(f"Service launched at: {service_manager.url}")
    print(f"Service status: {service_manager.status()}")
    print("Service is running. Press Ctrl+C to stop.")

    try:
        # Keep the service running
        while True:
            asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down service...")
        service_manager.shutdown()


def main():
    """Main function."""
    args = parse_arguments()

    if args.mode == "simple":
        asyncio.run(run_simple_bot(args.token, args.verbose))
    else:
        run_service_bot(args.token, args.port, args.verbose)


if __name__ == "__main__":
    main()
