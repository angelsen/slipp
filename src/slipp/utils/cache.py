"""Simple JSON-based cache with TTL support."""

import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from slipp import output
from slipp.utils.files import atomic_write_text


class Cache:
    """Simple file-based cache with TTL (Time To Live).

    Cache is stored as JSON in ~/.cache/slipp/cache.json (or
    $XDG_CACHE_HOME/slipp/cache.json). Multiple `Cache`
    instances within one process (e.g. one per host during parallel
    discovery) share a class-level thread lock and reload from disk on
    every read/write so concurrent instances don't clobber each other's
    entries. This does not guard against concurrent separate `slipp`
    processes, which have no cross-process file lock - acceptable since
    cache entries are TTL'd and losing one to a race just costs an extra
    network round trip, not correctness.

    Example:
        >>> cache = Cache()
        >>> cache.set('key', {'data': 'value'}, ttl_seconds=300)
        >>> value = cache.get('key')
        >>> print(value)
        {'data': 'value'}
    """

    _lock = threading.Lock()

    def __init__(self):
        """Initialize cache."""
        xdg_cache = os.getenv("XDG_CACHE_HOME")
        cache_dir = (
            Path(xdg_cache) / "slipp" if xdg_cache else Path.home() / ".cache" / "slipp"
        )

        self.cache_dir = cache_dir
        self.cache_file = cache_dir / "cache.json"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        """Load cache from disk.

        Returns:
            Cache dictionary
        """
        if not self.cache_file.exists():
            return {}

        try:
            with open(self.cache_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            output.warning(f"Failed to read cache {self.cache_file}: {e}")
            return {}

    def _save(self) -> None:
        """Save cache to disk."""
        try:
            content = json.dumps(self._cache, indent=2, default=str)
            atomic_write_text(self.cache_file, content)
        except (IOError, OSError) as e:
            output.warning(f"Failed to write cache {self.cache_file}: {e}")

    def get(self, key: str) -> Any | None:
        """Get value from cache if not expired.

        Reloads from disk under lock so a concurrent `Cache` instance's
        writes aren't missed.

        Args:
            key: Cache key

        Returns:
            Cached value or None if expired/missing
        """
        with self._lock:
            self._cache = self._load()

            if key not in self._cache:
                return None

            entry = self._cache[key]
            expires_str = entry.get("expires")
            if expires_str:
                expires = datetime.fromisoformat(expires_str)
                if datetime.now() > expires:
                    del self._cache[key]
                    self._save()
                    return None

            return entry.get("value")

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Set value in cache with TTL.

        Reloads from disk and merges under lock so concurrent `Cache`
        instances (e.g. one per host during parallel discovery) don't
        overwrite each other's entries.

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl_seconds: Time to live in seconds (default: 300 = 5 minutes)
        """
        expires = datetime.now() + timedelta(seconds=ttl_seconds)

        with self._lock:
            self._cache = self._load()
            self._cache[key] = {
                "value": value,
                "expires": expires.isoformat(),
            }
            self._save()
