"""Script loading, validation and text preparation."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from voiceover.voices import PREBUILT_VOICES, canonical_voice_name

SEGMENT_ID_PATTERN = r"^[A-Za-z0-9_-]+$"
PROJECT_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


class ConfigError(Exception):
    """Raised when a script file cannot be loaded or is invalid."""


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=SEGMENT_ID_PATTERN)
    text: str
    style: str | None = None

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("segment text must not be empty")
        return value

    @field_validator("style")
    @classmethod
    def blank_style_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class Script(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str = Field(pattern=PROJECT_PATTERN)
    voice: str
    language: str = "fr-FR"
    style: str = ""
    pronunciations: dict[str, str] = Field(default_factory=dict)
    segments: list[Segment] = Field(min_length=1)

    @field_validator("voice")
    @classmethod
    def voice_is_prebuilt(cls, value: str) -> str:
        return validate_voice(value)

    @field_validator("style")
    @classmethod
    def strip_style(cls, value: str) -> str:
        return value.strip()

    @field_validator("pronunciations")
    @classmethod
    def pronunciation_keys_not_empty(cls, value: dict[str, str]) -> dict[str, str]:
        for key in value:
            if not str(key).strip():
                raise ValueError("pronunciation keys must not be empty")
        return {str(k): str(v) for k, v in value.items()}

    @model_validator(mode="after")
    def unique_segment_ids(self) -> Script:
        seen: set[str] = set()
        duplicates: list[str] = []
        for segment in self.segments:
            if segment.id in seen:
                duplicates.append(segment.id)
            seen.add(segment.id)
        if duplicates:
            raise ValueError(f"duplicate segment ids: {', '.join(sorted(set(duplicates)))}")
        return self

    def segment(self, segment_id: str) -> Segment:
        for segment in self.segments:
            if segment.id == segment_id:
                return segment
        raise ConfigError(f"Unknown segment id: {segment_id}")

    def select(self, only: list[str] | None) -> list[Segment]:
        """Return segments in script order, optionally filtered by id."""
        if not only:
            return list(self.segments)
        known = {s.id for s in self.segments}
        unknown = [i for i in only if i not in known]
        if unknown:
            raise ConfigError(
                f"Unknown segment id(s): {', '.join(unknown)}. Known ids: {', '.join(sorted(known))}"
            )
        wanted = set(only)
        return [s for s in self.segments if s.id in wanted]

    def prepared_text(self, segment: Segment) -> str:
        return apply_pronunciations(segment.text, self.pronunciations)

    def combined_style(self, segment: Segment) -> str:
        return combine_styles(self.style, segment.style)


def validate_voice(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("voice must be set")
    canonical = canonical_voice_name(value)
    if canonical is None:
        raise ValueError(
            f"unknown prebuilt voice '{value}'. Valid voices: {', '.join(PREBUILT_VOICES)}"
        )
    return canonical


def apply_pronunciations(text: str, pronunciations: dict[str, str]) -> str:
    """Replace whole-word occurrences of each key with its spoken form.

    All keys are matched in a single pass (longest first), so a replacement
    is never re-processed by another rule.
    """
    if not pronunciations:
        return text
    keys = sorted(pronunciations, key=len, reverse=True)
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(k) for k in keys) + r")(?!\w)")
    return pattern.sub(lambda m: pronunciations[m.group(0)], text)


def combine_styles(global_style: str, segment_style: str | None) -> str:
    parts = [p.strip() for p in (global_style, segment_style or "") if p and p.strip()]
    return " ".join(parts)


def parse_id_list(value: str | None) -> list[str]:
    """Parse a comma-separated CLI value such as 'V03,V07'."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def load_script(path: Path) -> Script:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Script file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: the top level of the script must be a mapping")
    try:
        return Script.model_validate(raw)
    except ValidationError as exc:
        lines = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"]) or "<root>"
            lines.append(f"  - {location}: {error['msg']}")
        raise ConfigError(f"Invalid script {path}:\n" + "\n".join(lines)) from exc
