"""Data models for deployment operations.

This module defines the core data structures used throughout the launch and deploy
commands, including service detection, deployment configuration, and results.

All models use Pydantic v2 for validation and serialization.
"""

from pathlib import Path

from pydantic import BaseModel, Field, field_serializer

from slipp.models.host import AnsibleHost
from slipp.models.service import Runtime


class DetectedService(BaseModel):
    """Detected service from source code scan.

    Represents a framework detected by scanning the project directory,
    along with its configuration requirements for Docker deployment.

    Attributes:
        name: Service name (e.g., "backend", "frontend")
        framework: Framework identifier (e.g., "fastapi", "sveltekit")
        path: Absolute path to service directory
        port: Default port number for the service
        template_url: URL to Fly.io Dockerfile template
        dependencies: List of detected dependencies (e.g., ["fastapi", "asyncpg"])
        env_vars: Environment variables required by the service
    """

    name: str
    framework: str
    path: Path
    port: int
    template_url: str
    dependencies: list[str] = Field(default_factory=list)
    env_vars: dict[str, str] = Field(default_factory=dict)

    @field_serializer("path")
    def serialize_path(self, path: Path) -> str:
        """Serialize Path to string for JSON output."""
        return str(path)


class DeploymentHostConfig(AnsibleHost):
    """Deployment host configuration extending AnsibleHost.

    Extends AnsibleHost with deployment-specific metadata for Ansible inventory.
    Inherits: inventory_hostname, ansible_host, ansible_user, ansible_port from AnsibleHost.

    Supports both slipp-native and external projects:
    - slipp projects: All fields populated
    - External projects (MDAD): app_domain and admin_email are None

    Attributes:
        name: Ansible host identifier (same as inventory_hostname, kept for template compatibility)
        app_domain: Domain for the application (used by Caddy). Optional for external projects.
        admin_email: Admin email for Let's Encrypt HTTPS certificates. Optional for external projects.
        runtime: How the app runs (systemd, docker, podman; default: docker)
    """

    name: str = Field(..., min_length=1, description="Host identifier")
    app_domain: str | None = Field(default=None, description="Domain for app (Caddy)")
    admin_email: str | None = Field(
        default=None, description="Admin email for HTTPS certs"
    )
    runtime: Runtime = Field(
        default=Runtime.DOCKER, description="How the app runs (systemd, docker, podman)"
    )


class InventoryConfig(BaseModel):
    """Ansible inventory configuration.

    Manages inventory of deployment targets in standard Ansible format.

    Attributes:
        hosts: Dictionary of deployment host configurations keyed by name
               Supports both slipp-native projects (full config) and external projects (minimal config)
    """

    hosts: dict[str, DeploymentHostConfig] = Field(default_factory=dict)

    @classmethod
    def from_ansible_format(cls, data: dict) -> "InventoryConfig":
        """Parse from standard Ansible inventory format.

        Expected format:
        all:
          hosts:
            production:
              ansible_host: 1.2.3.4
              ansible_user: root
              ansible_port: 22
              app_domain: example.com
              admin_email: admin@example.com
              runtime: docker  # Optional, uses Pydantic default if missing (systemd/docker/podman)

        Args:
            data: Inventory data dict from YAML

        Returns:
            InventoryConfig instance
        """
        hosts_data = data.get("all", {}).get("hosts", {})
        hosts = {
            name: DeploymentHostConfig(name=name, inventory_hostname=name, **config)
            for name, config in hosts_data.items()
        }
        return cls(hosts=hosts)

    @classmethod
    def from_ansible_inventory_json(cls, data: dict) -> "InventoryConfig":
        """Parse from ansible-inventory --list JSON output.

        Expected structure:
        {
            "_meta": {
                "hostvars": {
                    "matrix.example.com": {
                        "ansible_host": "1.2.3.4",
                        "ansible_user": "root",
                        "ansible_port": 22,
                        ...other vars...
                    }
                }
            },
            "all": {...},
            "matrix_servers": {...}
        }

        Args:
            data: JSON output from ansible-inventory --list

        Returns:
            InventoryConfig with DeploymentHostConfig objects (minimal config for external projects)

        Notes:
            - Extracts SSH connection info (host, user, port)
            - Sets app_domain and admin_email to None (external projects)
            - Works with MDAD and any Ansible inventory structure
            - Hosts with no entry in _meta.hostvars (e.g. addressed only by
              group membership, no host-specific vars) still get a
              DeploymentHostConfig with defaulted connection info, so a
              valid var-less-host inventory isn't reported as having zero
              hosts.
        """
        hostvars = data.get("_meta", {}).get("hostvars", {})

        # dict.fromkeys preserves first-seen order (unlike a set, whose
        # iteration order depends on Python's per-process string hash seed
        # and is therefore not stable across runs).
        hostnames: dict[str, None] = dict.fromkeys(hostvars)
        for group_name, group in data.items():
            if group_name == "_meta":
                continue
            hostnames.update(dict.fromkeys(group.get("hosts", [])))

        hosts = {}
        for hostname in hostnames:
            vars = hostvars.get(hostname, {})
            user = vars.get("ansible_user") or vars.get("ansible_ssh_user") or "root"

            hosts[hostname] = DeploymentHostConfig(
                name=hostname,
                inventory_hostname=hostname,
                ansible_host=vars.get("ansible_host", hostname),
                ansible_user=user,
                ansible_port=vars.get("ansible_port", 22),
                app_domain=None,
                admin_email=None,
            )

        return cls(hosts=hosts)

    def to_ansible_format(self) -> dict:
        """Convert to standard Ansible inventory format.

        Returns:
            Dict in Ansible inventory format with all.hosts structure
        """
        return {
            "all": {
                "hosts": {name: host.model_dump() for name, host in self.hosts.items()}
            }
        }


class CaddySite(BaseModel):
    """Caddy site configuration for a service.

    Represents a single reverse proxy configuration.

    Attributes:
        domain: Domain or subdomain
        upstream_host: Backend host (default: localhost)
        upstream_port: Backend port
        path_prefix: Path routing (default: /)
    """

    domain: str = Field(description="Domain or subdomain")
    upstream_host: str = Field(default="localhost", description="Backend host")
    upstream_port: int = Field(description="Backend port")
    path_prefix: str = Field(default="/", description="Path routing")


class CaddyConfig(BaseModel):
    """Caddy role configuration.

    Configuration for Caddy reverse proxy setup.

    Attributes:
        sites: List of site configurations
        auto_https: Enable automatic HTTPS (default: True)
        sites_dir: Site configs directory (default: /etc/caddy/sites)
        staging: Use Let's Encrypt staging for testing (default: False)
    """

    sites: list[CaddySite] = Field(default_factory=list)
    auto_https: bool = Field(default=True, description="Enable automatic HTTPS")
    sites_dir: str = Field(
        default="/etc/caddy/sites", description="Site configs directory"
    )
    staging: bool = Field(
        default=False, description="Use Let's Encrypt staging for testing"
    )


class ProvisionConfig(BaseModel):
    """Complete provisioning configuration for playbook generation.

    Combines all configuration needed to generate Ansible project.

    Attributes:
        services: Detected services
        inventory: Inventory configuration
        project_name: Project name
        project_root: Absolute path to project
        caddy_config: Caddy configuration
        skip_caddy: Skip Caddy role generation (for --proxy none)
    """

    services: list[DetectedService] = Field(description="Detected services")
    inventory: InventoryConfig = Field(description="Inventory configuration")
    project_name: str = Field(description="Project name")
    project_root: Path = Field(description="Absolute path to project")
    caddy_config: CaddyConfig = Field(description="Caddy configuration")
    skip_caddy: bool = Field(default=False, description="Skip Caddy role generation")

    @field_serializer("project_root")
    def serialize_path(self, path: Path) -> str:
        """Serialize Path to string for JSON output."""
        return str(path)

    def to_dict(self) -> dict:
        """Convert to dict for template rendering.

        Returns:
            Dict with all fields formatted for Jinja2 templates
        """
        first_host = list(self.inventory.hosts.values())[0]

        return {
            "services": [s.model_dump() for s in self.services],
            "inventory": self.inventory.to_ansible_format(),
            "project_name": self.project_name,
            "project_root": str(self.project_root),
            "caddy_sites": [site.model_dump() for site in self.caddy_config.sites],
            "caddy_auto_https": self.caddy_config.auto_https,
            "caddy_sites_dir": self.caddy_config.sites_dir,
            "caddy_staging": self.caddy_config.staging,
            "skip_caddy": self.skip_caddy,
            "target_host": first_host.ansible_host,
            "ssh_user": first_host.ansible_user,
            "ssh_port": first_host.ansible_port,
            "app_domain": first_host.app_domain or "",
            "runtime": first_host.runtime,
        }


class ComposeConfig(BaseModel):
    """Context for docker-compose.yml template rendering.

    Attributes:
        services: Detected services
        project_name: Project name
        project_root: Project root directory for path relativization
    """

    services: list[DetectedService] = Field(description="Detected services")
    project_name: str = Field(description="Project name")
    project_root: Path = Field(description="Project root directory")

    def to_dict(self) -> dict:
        """Convert to dict for Jinja2 template context."""
        return {
            "services": [s.model_dump() for s in self.services],
            "project_name": self.project_name,
            "project_root": str(self.project_root),
        }
