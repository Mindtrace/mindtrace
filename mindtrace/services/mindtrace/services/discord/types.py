from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from mindtrace.core import TaskSchema


class DiscordEventType(Enum):
    """Types of Discord events that can be handled."""

    MESSAGE = "message"
    REACTION = "reaction"
    MEMBER_JOIN = "member_join"
    MEMBER_LEAVE = "member_leave"
    VOICE_STATE_UPDATE = "voice_state_update"
    GUILD_JOIN = "guild_join"
    GUILD_LEAVE = "guild_leave"


@dataclass
class DiscordCommand:
    """Represents a Discord command with its metadata."""

    name: str
    description: str
    usage: str
    aliases: List[str]
    category: str
    enabled: bool = True
    hidden: bool = False
    cooldown: Optional[int] = None
    permissions: Optional[List[str]] = None


class DiscordCommandInput(BaseModel):
    """Base input schema for Discord commands."""

    content: str
    author_id: Optional[int] = None
    channel_id: Optional[int] = None
    guild_id: Optional[int] = None
    message_id: Optional[int] = None


class DiscordCommandOutput(BaseModel):
    """Base output schema for Discord commands."""

    response: str
    embed: Optional[Dict[str, Any]] = None
    delete_after: Optional[float] = None


class DiscordStatusOutput(BaseModel):
    """Output schema for bot status."""

    bot_name: Optional[str] = None
    guild_count: int
    user_count: int
    latency: float
    status: str


class DiscordCommandsOutput(BaseModel):
    """Output schema for commands list."""

    commands: List[Dict[str, Any]]


class DiscordCommandSchema(TaskSchema):
    """Base schema for Discord commands."""

    name: str = "discord_command"
    input_schema: type[DiscordCommandInput] = DiscordCommandInput
    output_schema: type[DiscordCommandOutput] = DiscordCommandOutput


class DiscordStatusSchema(TaskSchema):
    """Schema for bot status endpoint."""

    name: str = "discord_status"
    output_schema: type[DiscordStatusOutput] = DiscordStatusOutput


class DiscordCommandsSchema(TaskSchema):
    """Schema for commands list endpoint."""

    name: str = "discord_commands"
    output_schema: type[DiscordCommandsOutput] = DiscordCommandsOutput


class DiscordEventHandler(ABC):
    """Abstract base class for Discord event handlers."""

    @abstractmethod
    async def handle(self, event_type: DiscordEventType, **kwargs) -> None:
        """Handle a Discord event."""
        pass  # pragma: no cover
