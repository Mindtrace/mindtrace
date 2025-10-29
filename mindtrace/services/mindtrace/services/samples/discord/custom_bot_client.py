"""Example usage of the Discord client implementation.

This file demonstrates how to create and use a Discord bot with the DiscordClient.
"""

import argparse
import asyncio

import discord

from mindtrace.services.discord.discord_client import DiscordClient, DiscordEventHandler, DiscordEventType


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


class CustomDiscordBot(DiscordClient):
    """Custom Discord bot with specific functionality."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Register custom event handlers
        self.register_event_handler(DiscordEventType.MESSAGE, CustomEventHandler())

        # Register slash commands immediately
        self.logger.info("Registering slash commands...")
        self._register_commands()
        self.logger.info(f"Registered {len(self.bot.tree.get_commands())} slash commands")

    def _register_commands(self):
        """Register the actual slash commands."""

        @self.bot.tree.command(name="info", description="Get server information")
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
                f"Created: {guild.created_at.strftime('%Y-%m-%d')}"
            )
            await interaction.response.send_message(response)

        @self.bot.tree.command(name="roll", description="Roll a dice")
        @discord.app_commands.describe(sides="Number of sides on the dice (default: 6)")
        async def roll_command(interaction: discord.Interaction, sides: int = 6):
            """Roll a dice."""
            if sides < 1:
                await interaction.response.send_message("Number of sides must be positive.", ephemeral=True)
                return

            import random

            result = random.randint(1, sides)
            response = f"🎲 You rolled a {result} (1-{sides})"
            await interaction.response.send_message(response)

        @self.bot.tree.command(name="cleanup", description="Clean up bot messages")
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

        @self.bot.tree.command(name="help", description="Show available commands")
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


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run a custom Discord bot with Mindtrace",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use token from config (MINDTRACE_DISCORD_BOT_TOKEN)
  python discord_bot_example.py
  
  # Override token from command line
  python discord_bot_example.py --token "your_token_here"
  
  # Set token via environment variable
  MINDTRACE_API_KEYS__DISCORD="your_token" python discord_bot_example.py
        """,
    )

    parser.add_argument(
        "--token", type=str, default=None, help="Discord bot token (overrides MINDTRACE_DISCORD_BOT_TOKEN from config)"
    )

    parser.add_argument(
        "--description", type=str, default="A custom Discord bot built with Mindtrace", help="Bot description"
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    return parser.parse_args()


async def main():
    """Main function to run the Discord bot."""
    args = parse_arguments()

    # Token priority:
    # 1. Command line argument (highest priority)
    # 2. Config value (MINDTRACE_DISCORD_BOT_TOKEN, handled by DiscordClient)
    token = args.token

    # If no token provided via command line, DiscordClient will use config
    if token is None:
        print("No token provided via --token.")
        print("The bot will attempt to use MINDTRACE_DISCORD_BOT_TOKEN from Mindtrace config.")

    # Create and configure the bot
    bot = CustomDiscordBot(
        token=token,  # This can be None, DiscordClient will use config
        description=args.description,
    )

    try:
        # Start the bot
        print("Starting Discord bot...")
        if args.verbose:
            print(f"Bot description: {args.description}")
            if token:
                print("Using token from command line")
            else:
                print("Using MINDTRACE_DISCORD_BOT_TOKEN from config")

        await bot.start_bot()
    except KeyboardInterrupt:
        print("\nShutting down bot...")
    except Exception as e:
        print(f"Error running bot: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
    finally:
        await bot.stop_bot()


if __name__ == "__main__":
    # Run the bot
    asyncio.run(main())
