"""Simple JSON-based cache with TTL support."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class Cache:
    """Simple file-based cache with TTL (Time To Live).

    Cache is stored as JSON in ~/.cache/slipp/cache.json

    Example:
        >>> cache = Cache()
        >>> cache.set('key', {'data': 'value'}, ttl_seconds=300)
        >>> value = cache.get('key')
        >>> print(value)
        {'data': 'value'}
    """

    def __init__(self):
        """Initialize cache."""
        cache_dir = Path.home() / ".cache" / "slipp"

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
        except (json.JSONDecodeError, IOError):
            return {}

    def _save(self) -> None:
        """Save cache to disk."""
        try:
            with open(self.cache_file, "w") as f:
                json.dump(self._cache, f, indent=2, default=str)
        except IOError:
            pass

    def get(self, key: str) -> Any | None:
        """Get value from cache if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if expired/missing
        """
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

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl_seconds: Time to live in seconds (default: 300 = 5 minutes)
        """
        expires = datetime.now() + timedelta(seconds=ttl_seconds)

        self._cache[key] = {
            "value": value,
            "expires": expires.isoformat(),
        }

        self._save()
