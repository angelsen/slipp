"""Base classes for secret pull sources."""

import base64
import json
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from slipp.utils.errors import SourceNotFoundError

SOURCES: dict[str, type["SecretSource"]] = {}


def register_source(source_cls: type["SecretSource"]) -> type["SecretSource"]:
    """Decorator to register a source class."""
    SOURCES[source_cls.name] = source_cls
    return source_cls


def get_source(name: str) -> "SecretSource":
    """Get source instance by name."""
    if name not in SOURCES:
        available = ", ".join(SOURCES.keys()) or "(none)"
        raise SourceNotFoundError(f"Unknown source '{name}'. Available: {available}")
    return SOURCES[name]()


def list_sources() -> list[str]:
    """List available source names."""
    return list(SOURCES.keys())


@dataclass
class PullSession:
    """Session for secrets pull operation."""

    session_secret: str
    port: int
    source: str

    def encode(self) -> str:
        """Encode session to URL-safe token for browser."""
        data = {
            "session": self.session_secret,
            "port": self.port,
            "source": self.source,
            "timestamp": datetime.now().isoformat(),
        }
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


class SecretSource(ABC):
    """Base class for secret pull sources."""

    name: str

    @abstractmethod
    def get_auth_url(self, session: PullSession) -> str:
        """Get URL to open in browser for authentication/selection."""
        pass

    @abstractmethod
    def parse_credentials(self, raw: list[dict]) -> dict[str, str]:
        """Parse raw credentials from callback into vault variables."""
        pass

    def get_description(self) -> str:
        """Human-readable description for --help."""
        return f"Pull secrets from {self.name}"


def find_available_port(start: int = 49152, end: int = 65535) -> int:
    """Find an available port in the dynamic/private range."""
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", port))
                return port
        except OSError:
            continue
    raise RuntimeError("No available ports")
