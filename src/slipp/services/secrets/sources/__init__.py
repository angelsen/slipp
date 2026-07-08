"""Secret pull sources registry."""

from slipp.services.secrets.sources.base import (
    PullSession,
    SecretSource,
    find_available_port,
)
from slipp.services.secrets.sources.nor_auth import NorAuthSource
from slipp.utils.errors import SourceNotFoundError

_SOURCES: dict[str, type[SecretSource]] = {
    NorAuthSource.name: NorAuthSource,
}


def get_source(name: str) -> SecretSource:
    """Get source instance by name."""
    if name not in _SOURCES:
        available = ", ".join(_SOURCES) or "(none)"
        raise SourceNotFoundError(f"Unknown source '{name}'. Available: {available}")
    return _SOURCES[name]()


def list_sources() -> list[str]:
    """List available source names."""
    return list(_SOURCES)


__all__ = [
    "PullSession",
    "SecretSource",
    "find_available_port",
    "get_source",
    "list_sources",
]
