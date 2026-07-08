"""Ansible host models with Pydantic v2 validation."""

from pathlib import Path

from pydantic import BaseModel, Field


class AnsibleHost(BaseModel):
    """Ansible inventory host configuration.

    Represents a host from Ansible inventory with all connection parameters.
    Maps directly to Ansible inventory format with inventory_hostname as the key.

    Attributes:
        inventory_hostname: Ansible inventory host identifier (e.g., "production", "matrix-main") [REQUIRED]
        ansible_host: IP address or domain for SSH connection [REQUIRED]
        ansible_user: SSH username (default: root)
        ansible_port: SSH port (default: 22, range: 1-65535)
        key_file: Optional path to SSH private key (for explicit key usage)
    """

    inventory_hostname: str = Field(
        ..., min_length=1, description="Ansible inventory host identifier"
    )
    ansible_host: str = Field(
        ..., min_length=1, description="IP or domain for SSH connection"
    )
    ansible_user: str = Field(default="root", description="SSH user")
    ansible_port: int = Field(default=22, ge=1, le=65535, description="SSH port")
    key_file: Path | None = Field(default=None, description="SSH private key path")

    def connection_string(self) -> str:
        """SSH connection string for display.

        Returns:
            Connection string in format: user@host:port
        """
        return f"{self.ansible_user}@{self.ansible_host}:{self.ansible_port}"
