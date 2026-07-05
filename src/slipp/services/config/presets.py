"""Tag preset resolution service.

Extracts preset resolution logic from deploy.py and tags.py.
Provides a service for resolving tag presets to Ansible tag arguments.
"""

import shlex

from slipp.models.local_config import LocalConfig
from slipp.services.config.local import LocalConfigService
from slipp.utils.errors import PresetNotFoundError


class PresetResolver:
    """Resolve tag presets from local config.

    This service handles the logic for resolving preset names
    to Ansible --tags and --skip-tags arguments.
    """

    def __init__(self, config: LocalConfig | None = None):
        """Initialize with optional config.

        Args:
            config: Local config to use (loads from cwd if None)
        """
        self.config = config or LocalConfigService.load()

    def resolve(self, preset_name: str) -> tuple[str | None, str | None]:
        """Resolve preset to (tags, skip_tags) tuple.

        Args:
            preset_name: Name of the preset to resolve

        Returns:
            Tuple of (tags, skip_tags) where each is a comma-separated string or None

        Raises:
            PresetNotFoundError: If preset doesn't exist
        """
        if not self.config:
            raise PresetNotFoundError(
                f"No config found, preset '{preset_name}' not available"
            )

        if preset_name not in self.config.tag_presets:
            raise PresetNotFoundError(f"Preset '{preset_name}' not found")

        args = self.config.tag_presets[preset_name]
        return parse_preset_args(args)

    def list_presets(self) -> dict[str, str]:
        """List all available presets.

        Returns:
            Dict mapping preset names to their argument strings
        """
        if not self.config:
            return {}
        return self.config.tag_presets.copy()

    def get_preset_args(self, preset_name: str) -> str | None:
        """Get the raw args string for a preset.

        Args:
            preset_name: Name of the preset

        Returns:
            Args string (e.g., "--tags setup-all --skip-tags foo") or None
        """
        if not self.config:
            return None
        return self.config.tag_presets.get(preset_name)


def parse_preset_args(args: str) -> tuple[str | None, str | None]:
    """Parse preset args string into tags and skip_tags.

    Args:
        args: String like "--tags setup-all --skip-tags foo,bar"

    Returns:
        Tuple of (tags, skip_tags)

    Examples:
        >>> parse_preset_args("--tags setup-all")
        ('setup-all', None)
        >>> parse_preset_args("--tags setup-all --skip-tags foo,bar")
        ('setup-all', 'foo,bar')
    """
    tokens = shlex.split(args)
    tags = None
    skip_tags = None

    i = 0
    while i < len(tokens):
        if tokens[i] in ("--tags", "-t") and i + 1 < len(tokens):
            tags = tokens[i + 1]
            i += 2
        elif tokens[i] == "--skip-tags" and i + 1 < len(tokens):
            skip_tags = tokens[i + 1]
            i += 2
        else:
            i += 1

    return tags, skip_tags
