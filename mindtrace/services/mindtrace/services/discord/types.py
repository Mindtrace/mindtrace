from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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


# ---------------------------------------------------------------------------
# Lightweight interaction types for executing Discord commands via HTTP API.
# ---------------------------------------------------------------------------


@dataclass
class CapturedCall:
    """An async callable that records whether it was invoked and with what arguments.

    Used to capture responses from Discord command callbacks when executing
    commands programmatically via the HTTP API.
    """

    called: bool = False
    call_args: tuple = ()

    async def __call__(self, *args, **kwargs):
        self.called = True
        self.call_args = (args, kwargs)


@dataclass
class APIUser:
    """Minimal user representation for programmatic command execution."""

    id: int | None
    mention: str
    display_name: str


@dataclass
class APIGuild:
    """Minimal guild representation for programmatic command execution."""

    id: int
    _member: APIUser | None = field(default=None, repr=False)

    def get_member(self, member_id: int) -> APIUser | None:
        return self._member


@dataclass
class APIChannel:
    """Minimal channel representation for programmatic command execution."""

    id: int | None


@dataclass
class APIResponse:
    """Captures calls to interaction.response methods."""

    send_message: CapturedCall = field(default_factory=CapturedCall)
    defer: CapturedCall = field(default_factory=CapturedCall)


@dataclass
class APIFollowup:
    """Captures calls to interaction.followup methods."""

    send: CapturedCall = field(default_factory=CapturedCall)


@dataclass
class APIInteraction:
    """Lightweight Discord interaction for executing commands via the HTTP API.

    Provides the minimal interface that Discord slash command callbacks expect,
    without depending on discord.py internals.
    """

    user: APIUser
    guild: APIGuild | None
    channel: APIChannel
    message_id: int | None
    response: APIResponse = field(default_factory=APIResponse)
    followup: APIFollowup = field(default_factory=APIFollowup)
