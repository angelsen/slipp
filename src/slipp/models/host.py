"""Ansible host models with Pydantic v2 validation."""

from pydantic import BaseModel, Field

from slipp.constants import DEFAULT_SSH_PORT, DEFAULT_SSH_USER
from slipp.models.types import OptionalPathStr


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
    ansible_user: str = Field(default=DEFAULT_SSH_USER, description="SSH user")
    ansible_port: int = Field(
        default=DEFAULT_SSH_PORT, ge=1, le=65535, description="SSH port"
    )
    key_file: OptionalPathStr = Field(default=None, description="SSH private key path")

    @property
    def connection_string(self) -> str:
        """SSH connection string for display.

        Returns:
            Connection string in format: user@host:port
        """
        return f"{self.ansible_user}@{self.ansible_host}:{self.ansible_port}"

    @property
    def ssh_target(self) -> str:
        """SSH positional target (no port -- port is a separate -p flag).

        Returns:
            Target string in format: user@host
        """
        return f"{self.ansible_user}@{self.ansible_host}"

    def to_ini_line(self) -> str:
        """Format as an Ansible INI inventory host line.

        Returns:
            e.g. "myhost ansible_host=1.2.3.4 ansible_user=root ansible_port=2222"
        """
        parts = [
            self.inventory_hostname,
            f"ansible_host={self.ansible_host}",
            f"ansible_user={self.ansible_user}",
        ]
        if self.ansible_port != DEFAULT_SSH_PORT:
            parts.append(f"ansible_port={self.ansible_port}")
        if self.key_file:
            parts.append(f"ansible_ssh_private_key_file={self.key_file}")
        return " ".join(parts)
