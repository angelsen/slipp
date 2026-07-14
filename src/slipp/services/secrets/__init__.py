"""Secrets management services for external sources."""

from slipp.services.secrets.nor_auth import NorAuthSource
from slipp.utils.errors import SourceNotFoundError


def get_source(name: str) -> NorAuthSource:
    """Validate a user-supplied source name and return its source instance."""
    if name != NorAuthSource.name:
        raise SourceNotFoundError(
            f"Unknown source '{name}'. Available: {NorAuthSource.name}"
        )
    return NorAuthSource()


__all__ = [
    "get_source",
]
