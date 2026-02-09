"""Model profiles for describing model capabilities.

A ModelProfile describes how requests to and responses from specific models
or families of models need to be constructed and processed to get the best results.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, fields, replace
from textwrap import dedent

from typing_extensions import Self

__all__ = [
    'ModelProfile',
    'ModelProfileSpec',
    'DEFAULT_PROFILE',
]


@dataclass(kw_only=True)
class ModelProfile:
    """Describes how requests to and responses from specific models or families of models need to be constructed and processed to get the best results.
    
    This is independent of the model and provider classes used.
    """

    supports_tools: bool = True
    """Whether the model supports tools (function calling).
    
    If True, the model can return structured tool calls in its response.
    If False, tools must be handled via prompted output or text parsing.
    """

    supports_json_schema_output: bool = False
    """Whether the model supports JSON schema output.
    
    This is also referred to as 'native' support for structured output.
    The model can enforce output matching a JSON schema natively.
    """

    supports_json_object_output: bool = False
    """Whether the model supports a dedicated mode to enforce JSON output, without necessarily sending a schema.
    
    E.g. OpenAI's JSON mode - the model is instructed to return JSON but
    doesn't receive a full schema.
    """

    default_structured_output_mode: str = 'tool'
    """The default structured output mode to use for the model.
    
    Options:
    - 'tool': Use tool calling for structured output
    - 'native': Use native JSON schema support
    - 'prompted': Use prompted output (instruct model to return JSON)
    """

    prompted_output_template: str = dedent(
        """
        Always respond with a JSON object that's compatible with this schema:

        {schema}

        Don't include any text or Markdown fencing before or after.
        """
    )
    """The instructions template to use for prompted structured output.
    
    The '{schema}' placeholder will be replaced with the JSON schema for the output.
    """

    json_schema_transformer: type | None = None
    """The transformer class to use to make JSON schemas compatible with the model.
    
    Some models require specific JSON schema formats. This transformer
    can adapt schemas to match the model's requirements.
    """

    thinking_tags: tuple[str, str] = ('<think>', '</think>')
    """The tags used to indicate thinking parts in the model's output."""

    ignore_streamed_leading_whitespace: bool = False
    """Whether to ignore leading whitespace when streaming a response.
    
    This is a workaround for models that emit empty text parts ahead of tool calls.
    """

    @classmethod
    def from_profile(cls, profile: ModelProfile | None) -> Self:
        """Build a ModelProfile subclass instance from a ModelProfile instance."""
        if isinstance(profile, cls):
            return profile
        return cls().update(profile)

    def update(self, profile: ModelProfile | None) -> Self:
        """Update this ModelProfile instance with the non-default values from another ModelProfile instance.
        
        Args:
            profile: The profile to update from.
        
        Returns:
            A new ModelProfile instance with updated values.
        """
        if not profile:
            return self
        field_names = set(f.name for f in fields(self))
        non_default_attrs = {
            f.name: getattr(profile, f.name)
            for f in fields(profile)
            if f.name in field_names and getattr(profile, f.name) != f.default
        }
        return replace(self, **non_default_attrs)


ModelProfileSpec = ModelProfile | Callable[[str], ModelProfile | None]
"""A model profile specification.
    
Can be either:
- A ModelProfile instance
- A function that takes a model name and returns a ModelProfile or None
"""

DEFAULT_PROFILE = ModelProfile()
"""The default model profile with standard settings."""
