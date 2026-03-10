from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from textwrap import dedent

from typing_extensions import Self

__all__ = ["ModelProfile", "ModelProfileSpec", "DEFAULT_PROFILE"]


@dataclass(kw_only=True)
class ModelProfile:
    supports_tools: bool = True
    supports_json_schema_output: bool = False
    supports_json_object_output: bool = False
    default_structured_output_mode: str = "tool"
    prompted_output_template: str = dedent(
        """
        Always respond with a JSON object that's compatible with this schema:

        {schema}

        Don't include any text or Markdown fencing before or after.
        """
    )
    json_schema_transformer: type | None = None
    thinking_tags: tuple[str, str] = ("<think>", "</think>")
    ignore_streamed_leading_whitespace: bool = False

    @classmethod
    def from_profile(cls, profile: ModelProfile | None) -> Self:
        if isinstance(profile, cls):
            return profile
        return cls().update(profile)

    def update(self, profile: ModelProfile | None) -> Self:
        if not profile:
            return self
        field_names = {f.name for f in fields(self)}
        non_default_attrs = {
            f.name: getattr(profile, f.name)
            for f in fields(profile)
            if f.name in field_names and getattr(profile, f.name) != f.default
        }
        return replace(self, **non_default_attrs)


ModelProfileSpec = ModelProfile | Callable[[str], ModelProfile | None]

DEFAULT_PROFILE = ModelProfile()
