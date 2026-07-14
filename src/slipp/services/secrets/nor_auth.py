"""nor-auth secret source, plus the pull-session helpers it consumes."""

import base64
import json
import os
import re
import socket
from dataclasses import dataclass
from datetime import datetime

from slipp import output
from slipp.utils.errors import PullError


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
    raise PullError("No available ports")


class NorAuthSource:
    """Pull secrets from nor-auth console."""

    name = "nor-auth"

    def get_auth_url(self, session: PullSession) -> str:
        """Open nor-auth export page for resource selection."""
        base_url = os.getenv("NOR_AUTH_URL", "https://console.nor.dev")
        token = session.encode()
        return f"{base_url}/export?session={token}"

    def parse_credentials(self, raw: list[dict]) -> dict[str, str]:
        """Parse nor-auth credentials into vault variables.

        Raises:
            PullError: If a resource is missing a required field.
        """
        result: dict[str, str] = {}

        for resource in raw:
            resource_type = resource.get("type")

            if resource_type == "bot":
                name = self._sanitize_name(resource.get("name", "bot"))
                self._check_collision(
                    result, f"vault_nor_bot_{name}_access_token", name
                )
                result.update(
                    {
                        f"vault_nor_bot_{name}_access_token": self._require(
                            resource, "accessToken"
                        ),
                        f"vault_nor_bot_{name}_device_id": self._require(
                            resource, "deviceId"
                        ),
                        f"vault_nor_bot_{name}_user_id": self._require(
                            resource, "userId"
                        ),
                        f"vault_nor_bot_{name}_homeserver": self._require(
                            resource, "homeserver"
                        ),
                    }
                )
            elif resource_type == "key":
                name = self._sanitize_name(resource.get("name", "api_key"))
                key = f"vault_nor_api_key_{name}"
                self._check_collision(result, key, name)
                result[key] = self._require(resource, "apiKey")
            else:
                output.warning(f"Skipping unknown credential type: {resource_type!r}")

        return result

    def _check_collision(self, result: dict[str, str], key: str, name: str) -> None:
        """Raise if a prior resource already claimed this sanitized name.

        Two resources with distinct display names can sanitize to the same
        vault key (e.g. "Bot 1" and "Bot-1" both -> "bot_1", or two
        unnamed resources both defaulting to "bot"/"api_key"). Without this
        check, the second resource's `result.update`/assignment silently
        overwrites the first's credentials with no error or warning.
        """
        if key in result:
            raise PullError(
                f"Duplicate credential name after sanitizing: {name!r} "
                "collides with another resource -- rename one in nor-auth"
            )

    def _require(self, resource: dict, key: str) -> str:
        """Fetch a required field, raising PullError if missing."""
        if key not in resource:
            resource_type = resource.get("type", "unknown")
            raise PullError(
                f"Malformed {resource_type} credential from nor-auth: missing '{key}'"
            )
        return resource[key]

    def _sanitize_name(self, name: str) -> str:
        """Convert name to vault-safe identifier.

        Strips everything but alphanumerics/underscores so a crafted
        display name (e.g. containing ':' or '\\n') can't inject extra
        YAML keys or plaintext lines into the vault file.
        """
        return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_") or "_"

    def get_description(self) -> str:
        """Human-readable description for --help."""
        return "Pull bot credentials from nor-auth"
