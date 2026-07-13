"""Secrets management services for external sources."""

from slipp.services.secrets.nor_auth import NorAuthSource
from slipp.utils.errors import SourceNotFoundError


def get_source(name: str) -> NorAuthSource:
    """Get source instance by name."""
    if name != NorAuthSource.name:
        raise SourceNotFoundError(
            f"Unknown source '{name}'. Available: {NorAuthSource.name}"
        )
    return NorAuthSource()


def list_sources() -> list[str]:
    """List available source names."""
    return [NorAuthSource.name]


__all__ = [
    "get_source",
    "list_sources",
]
