"""Secrets management services for external sources."""

from slipp.services.secrets.sources import (
    get_source,
    list_sources,
)

__all__ = [
    "get_source",
    "list_sources",
]
