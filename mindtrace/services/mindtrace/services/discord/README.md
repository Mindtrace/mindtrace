# Discord Client Implementation

This module provides a comprehensive Discord client implementation for Mindtrace services, built on top of the `discord.py` library. It follows the Mindtrace Service patterns and provides a clean, extensible interface for creating Discord bots.

## How Discord.py Works

Discord.py is a modern, easy-to-use Python library for Discord's API. Here's how it works:

### Core Concepts

1. **Bot Instance**: A `discord.ext.commands.Bot` object that represents your Discord bot
2. **Commands**: Functions decorated with `@bot.command()` that respond to user messages
3. **Events**: Functions decorated with `@bot.event` that respond to Discord events
4. **Intents**: Permissions that determine what data your bot can access
5. **Context**: Contains information about the command invocation (user, channel, guild, etc.)

### Basic Discord.py Example

```python
import discord
from discord.ext import commands

# Create bot with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot is ready: {bot.user}')

@bot.command()
async def ping(ctx):
    await ctx.send(f'Pong! Latency: {round(bot.latency * 1000)}ms')

bot.run('YOUR_TOKEN')
```

## Mindtrace Discord Client Features

Our implementation extends Discord.py with Mindtrace-specific features:

### 1. Service Integration
- Inherits from `mindtrace.services.Service`
- Provides HTTP endpoints for bot management
- Integrates with Mindtrace logging and configuration

### 2. Command Management
- Centralized command registration
- Command metadata (description, usage, permissions)
- Category organization
- Enable/disable commands dynamically

### 3. Event Handling System
- Abstract event handler interface
- Multiple handlers per event type
- Error handling and logging

### 4. Configuration
- Environment-based configuration
- Intents management
- Customizable command prefixes

## Usage Examples

### Basic Bot Setup

```python
from mindtrace.services.discord.discord_client import BaseDiscordClient
import os

class MyBot(BaseDiscordClient):
    def __init__(self):
        super().__init__(
            token=os.getenv("DISCORD_BOT_TOKEN"),
            command_prefix="!",
            description="My custom Discord bot"
        )
        
        # Register commands
        self.register_command(
            name="hello",
            description="Say hello",
            usage="!hello",
            handler=self.hello_command
        )
    
    async def hello_command(self, ctx, *args):
        return f"Hello {ctx.author.name}!"

# Run the bot
bot = MyBot()
await bot.start_bot()
```

### Custom Event Handlers

```python
from mindtrace.services.discord.discord_client import DiscordEventHandler, DiscordEventType

class WelcomeHandler(DiscordEventHandler):
    async def handle(self, event_type: DiscordEventType, **kwargs):
        if event_type == DiscordEventType.MEMBER_JOIN:
            member = kwargs.get('member')
            channel = member.guild.system_channel
            if channel:
                await channel.send(f"Welcome {member.mention}!")

# Register the handler
bot.register_event_handler(DiscordEventType.MEMBER_JOIN, WelcomeHandler())
```

### Advanced Commands

```python
async def moderation_command(self, ctx, *args):
    """Example moderation command with permissions."""
    if not ctx.author.guild_permissions.manage_messages:
        return "You need 'Manage Messages' permission to use this command."
    
    # Command logic here
    return "Moderation action completed."

# Register with permissions
self.register_command(
    name="moderate",
    description="Moderation command",
    usage="!moderate <action>",
    handler=self.moderation_command,
    permissions=["manage_messages"],
    category="Moderation"
)
```

## API Endpoints

The Discord client provides several HTTP endpoints:

- `GET /discord/status` - Get bot status information
- `GET /discord/commands` - List all registered commands
- `POST /discord/execute` - Execute commands programmatically

## Configuration

### Environment Variables

```bash
# Required
DISCORD_BOT_TOKEN=your_bot_token_here

# Optional
DISCORD_COMMAND_PREFIX=!
DISCORD_INTENTS=default
```

### Bot Token Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to the "Bot" section
4. Create a bot and copy the token
5. Set the token as an environment variable

### Intents Configuration

```python
import discord

# Default intents (recommended for most bots)
intents = discord.Intents.default()
intents.message_content = True

# All intents (use with caution)
intents = discord.Intents.all()

# Custom intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
```

## Best Practices

### 1. Error Handling
Always wrap command handlers in try-catch blocks:

```python
async def safe_command(self, ctx, *args):
    try:
        # Command logic
        return "Success!"
    except Exception as e:
        self.logger.error(f"Command error: {e}")
        return "An error occurred."
```

### 2. Permission Checking
Check permissions before executing sensitive commands:

```python
async def admin_command(self, ctx, *args):
    if not ctx.author.guild_permissions.administrator:
        return "You need administrator permissions."
    # Command logic
```

### 3. Rate Limiting
Implement cooldowns for commands that might be spam:

```python
self.register_command(
    name="spammy",
    description="A command with cooldown",
    usage="!spammy",
    handler=self.spammy_command,
    cooldown=30  # 30 seconds
)
```

### 4. Logging
Use the built-in logger for debugging:

```python
self.logger.info(f"Command executed: {ctx.command}")
self.logger.error(f"Error in command: {e}")
```

## Extending the Client

### Custom Command Categories

```python
class AdminCommands:
    """Admin command category."""
    
    @staticmethod
    async def ban_user(ctx, *args):
        # Ban logic
        pass

class FunCommands:
    """Fun command category."""
    
    @staticmethod
    async def roll_dice(ctx, *args):
        # Dice rolling logic
        pass

# Register categories
for method_name, method in AdminCommands.__dict__.items():
    if callable(method) and not method_name.startswith('_'):
        bot.register_command(
            name=method_name,
            description=f"Admin command: {method_name}",
            usage=f"!{method_name}",
            handler=method,
            category="Admin"
        )
```

### Custom Event Types

```python
from enum import Enum

class CustomEventType(Enum):
    CUSTOM_EVENT = "custom_event"

# Extend the DiscordEventType enum
DiscordEventType.CUSTOM_EVENT = CustomEventType.CUSTOM_EVENT
```

## Troubleshooting

### Common Issues

1. **Bot not responding**: Check if intents are properly configured
2. **Permission errors**: Verify bot has required permissions in Discord
3. **Token issues**: Ensure bot token is valid and not exposed
4. **Rate limiting**: Implement cooldowns for frequently used commands

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Security Considerations

1. **Never expose your bot token** in code or logs
2. **Use environment variables** for sensitive configuration
3. **Implement proper permission checks** for all commands
4. **Validate user input** to prevent injection attacks
5. **Use HTTPS** for all external API calls

## Performance Tips

1. **Use async/await** for all I/O operations
2. **Implement caching** for frequently accessed data
3. **Use pagination** for large data sets
4. **Monitor memory usage** for long-running bots
5. **Implement proper cleanup** in shutdown handlers 
