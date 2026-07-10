"""Global constants for slipp.

This module centralizes all hardcoded values used across the codebase,
making them easy to find, understand, and modify.
"""

from enum import StrEnum


class OutputFormat(StrEnum):
    """Output format for CLI commands.

    Used as global option: slipp -o json ps
    """

    table = "table"
    json = "json"


class SecretEncoding(StrEnum):
    """Output encoding for generated secrets.

    Used by: slipp secret / slipp secrets add / slipp secrets sync
    """

    hex = "hex"
    base64 = "base64"
    ulid = "ulid"


DEFAULT_ENV = "production"

DEFAULT_GALAXY_PATH = "roles/galaxy"


def get_inventory_filename(environment: str) -> str:
    """Get inventory filename for environment.

    Follows Ansible community conventions:
    - production → inventory.yml (backwards compatible, default)
    - dev/staging/etc → inventory-{environment}.yml (explicit naming)

    Args:
        environment: Environment name (production, dev, staging, etc.)

    Returns:
        Filename string (e.g., "inventory.yml" or "inventory-dev.yml")

    Examples:
        >>> get_inventory_filename("production")
        'inventory.yml'
        >>> get_inventory_filename("dev")
        'inventory-dev.yml'
        >>> get_inventory_filename("staging")
        'inventory-staging.yml'
    """
    return (
        "inventory.yml"
        if environment == DEFAULT_ENV
        else f"inventory-{environment}.yml"
    )


PLAYBOOK_FILENAME = "playbook.yml"

DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USER = "root"

VALID_PROXIES = ["caddy", "none", "wg-manage"]
