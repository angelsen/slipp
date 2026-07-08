"""Shared helpers for secret pull sources."""

import base64
import json
import socket
from dataclasses import dataclass
from datetime import datetime

from slipp.utils.errors import SlippError


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


def find_available_port(start: int = 49152, end: int = 65535) -> int:
    """Find an available port in the dynamic/private range."""
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", port))
                return port
        except OSError:
            continue
    raise SlippError("No available ports")
