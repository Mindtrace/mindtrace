"""Example usage of the Discord service implementation.

This file demonstrates how to create and use a Discord bot service with the DiscordService.
"""

import argparse

import discord

from mindtrace.services.discord import DiscordEventHandler, DiscordEventType, DiscordService


class CustomEventHandler(DiscordEventHandler):
    """Custom event handler for demonstration."""

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


class CustomDiscordService(DiscordService):
    """Custom Discord service with specific functionality."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Register custom event handlers
        self.register_event_handler(DiscordEventType.MESSAGE, CustomEventHandler())

        # Register slash commands immediately
        self.logger.info("Registering slash commands...")
        self._register_commands()
        self.logger.info(f"Registered {len(self.discord_client.bot.tree.get_commands())} slash commands")

    def _register_commands(self):
        """Register the actual slash commands."""

        @self.discord_client.bot.tree.command(name="info", description="Get server information")
        async def info_command(interaction: discord.Interaction):
            """Get server information."""
            self.logger.info(f"Info command called by {interaction.user}")
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

        @self.discord_client.bot.tree.command(name="roll", description="Roll a dice")
        @discord.app_commands.describe(sides="Number of sides on the dice (default: 6)")
        async def roll_command(interaction: discord.Interaction, sides: int = 6):
            """Roll a dice."""
            if sides < 1:
                await interaction.response.send_message("Number of sides must be positive.", ephemeral=True)
                return

            import random

            result = random.randint(1, sides)
            response = f"You rolled a {result} (1-{sides})"
            await interaction.response.send_message(response)

        @self.discord_client.bot.tree.command(name="cleanup", description="Clean up bot messages")
        @discord.app_commands.describe(count="Number of messages to delete (default: 10, max: 100)")
        async def cleanup_command(interaction: discord.Interaction, count: int = 10):
            """Clean up bot messages."""
            # Check permissions
            if not interaction.guild:
                await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
                return

            member = interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_messages:
                await interaction.response.send_message(
                    "You need the 'Manage Messages' permission to use this command.", ephemeral=True
                )
                return

            if count < 1 or count > 100:
                await interaction.response.send_message("Please specify a number between 1 and 100.", ephemeral=True)
                return

            # Defer response since this might take time
            await interaction.response.defer()

            deleted = 0
            async for message in interaction.channel.history(limit=count):
                if message.author == interaction.client.user:
                    await message.delete()
                    deleted += 1

            await interaction.followup.send(f"Cleaned up {deleted} bot messages.")

        @self.discord_client.bot.tree.command(name="help", description="Show available commands")
        async def help_command(interaction: discord.Interaction):
            """Show available commands."""
            commands_list = [
                "**/info** - Get server information",
                "**/roll [sides]** - Roll a dice",
                "**/cleanup [count]** - Clean up bot messages",
                "**/help** - Show this help message",
            ]
            response = "Available commands:\n" + "\n".join(commands_list)
            await interaction.response.send_message(response)

        @self.discord_client.bot.tree.command(name="service", description="Get service status")
        async def service_command(interaction: discord.Interaction):
            """Get service status via HTTP API."""
            try:
                # Use the service's HTTP API to get status
                status = self.get_bot_status(None)
                response = (
                    f"**Service Status**\n"
                    f"Bot: {status.bot_name or 'Not connected'}\n"
                    f"Guilds: {status.guild_count}\n"
                    f"Users: {status.user_count}\n"
                    f"Latency: {status.latency:.2f}ms\n"
                    f"Status: {status.status}\n"
                    f"Service ID: {self.id}"
                )
                await interaction.response.send_message(response)
            except Exception as e:
                await interaction.response.send_message(f"Error getting service status: {str(e)}", ephemeral=True)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run a custom Discord bot service with Mindtrace",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use token from config (MINDTRACE_DISCORD_BOT_TOKEN)
  python custom_bot_service.py
  
  # Override token from command line
  python custom_bot_service.py --token "your_token_here"
  
  # Set token via environment variable
  MINDTRACE_API_KEYS__DISCORD="your_token" python custom_bot_service.py
  
  # Run on specific port
  python custom_bot_service.py --port 8080
  
  # Run with custom host
  python custom_bot_service.py --host 0.0.0.0 --port 8080
        """,
    )

    parser.add_argument(
        "--token", type=str, default=None, help="Discord bot token (overrides MINDTRACE_DISCORD_BOT_TOKEN from config)"
    )

    parser.add_argument(
        "--host", type=str, default="localhost", help="Host to bind the service to (default: localhost)"
    )

    parser.add_argument("--port", type=int, default=8080, help="Port to run the service on (default: 8080)")

    parser.add_argument(
        "--description",
        type=str,
        default="A custom Discord bot service built with Mindtrace",
        help="Service description",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    return parser.parse_args()


def main():
    """Main function to run the Discord service."""
    args = parse_arguments()

    # Token priority:
    # 1. Command line argument (highest priority)
    # 2. Config value (MINDTRACE_DISCORD_BOT_TOKEN, handled by DiscordService)
    token = args.token

    # If no token provided via command line, DiscordService will use config
    if token is None:
        print("No token provided via --token.")
        print("The service will attempt to use MINDTRACE_DISCORD_BOT_TOKEN from Mindtrace config.")

    try:
        # Launch the service using the Service.launch() pattern
        print(f"Starting Discord service on {args.host}:{args.port}...")
        if args.verbose:
            print(f"Service description: {args.description}")
            if token:
                print("Using token from command line")
            else:
                print("Using MINDTRACE_DISCORD_BOT_TOKEN from config")

        # Launch the service
        service_manager = CustomDiscordService.launch(
            host=args.host, port=args.port, token=token, wait_for_launch=True, timeout=30
        )

        print(f"Service launched at: {service_manager.url}")
        print(f"Service status: {service_manager.status()}")
        print("Service is running. Press Ctrl+C to stop.")

        # Keep the service running
        try:
            while True:
                import time

                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down service...")
            service_manager.shutdown()

    except Exception as e:
        print(f"Error running service: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    # Run the service
    main()
