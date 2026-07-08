"""nor-auth secret source implementation."""

import os

from slipp.services.secrets.sources.base import PullSession


class NorAuthSource:
    """Pull secrets from nor-auth console."""

    name = "nor-auth"

    def get_auth_url(self, session: PullSession) -> str:
        """Open nor-auth export page for resource selection."""
        base_url = os.getenv("NOR_AUTH_URL", "https://console.nor.dev")
        token = session.encode()
        return f"{base_url}/export?session={token}"

    def parse_credentials(self, raw: list[dict]) -> dict[str, str]:
        """Parse nor-auth credentials into vault variables."""
        result: dict[str, str] = {}

        for resource in raw:
            resource_type = resource.get("type")

            if resource_type == "bot":
                name = self._sanitize_name(resource.get("name", "bot"))
                result.update(
                    {
                        f"vault_nor_bot_{name}_access_token": resource["accessToken"],
                        f"vault_nor_bot_{name}_device_id": resource["deviceId"],
                        f"vault_nor_bot_{name}_user_id": resource["userId"],
                        f"vault_nor_bot_{name}_homeserver": resource["homeserver"],
                    }
                )
            elif resource_type == "key":
                name = self._sanitize_name(resource.get("name", "api_key"))
                result[f"vault_nor_api_key_{name}"] = resource["apiKey"]

        return result

    def _sanitize_name(self, name: str) -> str:
        """Convert name to vault-safe identifier."""
        return name.lower().replace(" ", "_").replace("-", "_")

    def get_description(self) -> str:
        """Human-readable description for --help."""
        return "Pull bot credentials from nor-auth"
