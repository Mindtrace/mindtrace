import logging

from discord.ext import commands

from mindtrace.services.discord.discord_client import BaseDiscordClient
from mindtrace.services.discord.types import DiscordEventHandler, DiscordEventType


# Example command handlers
async def ping_command(ctx: commands.Context, *args) -> str:
    """Example ping command."""
    return f"Pong! Latency: {round(ctx.bot.latency * 1000)}ms"


async def echo_command(ctx: commands.Context, *args) -> str:
    """Example echo command."""
    if not args:
        return "Please provide a message to echo."
    return " ".join(args)


async def help_command(ctx: commands.Context, *args) -> str:
    """Example help command."""
    client = ctx.bot
    if hasattr(client, "_commands"):
        commands_list = []
        for cmd in client._commands.values():
            if not cmd.hidden:
                commands_list.append(f"**{cmd.name}**: {cmd.description}")

        return "Available commands:\n" + "\n".join(commands_list)
    return "No commands available."


# Example event handler
class LoggingEventHandler(DiscordEventHandler):
    """Example event handler that logs events."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    async def handle(self, event_type: DiscordEventType, **kwargs):
        """Handle events by logging them."""
        if event_type == DiscordEventType.MESSAGE:
            message = kwargs.get("message")
            self.logger.info(f"Message from {message.author}: {message.content}")
        elif event_type == DiscordEventType.MEMBER_JOIN:
            member = kwargs.get("member")
            self.logger.info(f"Member joined: {member.name}")
        elif event_type == DiscordEventType.MEMBER_LEAVE:
            member = kwargs.get("member")
            self.logger.info(f"Member left: {member.name}")


# Example bot implementation
class ExampleDiscordBot(BaseDiscordClient):
    """Example Discord bot implementation."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Register commands
        self.register_command(name="ping", description="Check bot latency", usage="!ping", handler=ping_command)

        self.register_command(name="echo", description="Echo a message", usage="!echo <message>", handler=echo_command)

        self.register_command(name="help", description="Show available commands", usage="!help", handler=help_command)

        # Register event handlers
        self.register_event_handler(DiscordEventType.MESSAGE, LoggingEventHandler(self.logger))
        self.register_event_handler(DiscordEventType.MEMBER_JOIN, LoggingEventHandler(self.logger))
        self.register_event_handler(DiscordEventType.MEMBER_LEAVE, LoggingEventHandler(self.logger))
