"""Shared Pydantic field types.

Annotated aliases for field-serialization patterns repeated across models.
"""

from pathlib import Path
from typing import Annotated

from pydantic import PlainSerializer

PathStr = Annotated[Path, PlainSerializer(lambda p: str(p), return_type=str)]
"""A required Path field that serializes to a plain string for JSON/YAML output."""

OptionalPathStr = Annotated[
    Path | None,
    PlainSerializer(lambda p: str(p) if p else None, return_type=str | None),
]
"""An optional Path field that serializes to a string, or None, for JSON/YAML output."""
