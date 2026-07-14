"""Deployment topology models: detected services, hosts, and inventory.

Caddy-specific config lives in models/caddy.py, compose template context in
models/compose.py -- both import DetectedService/ProvisionConfig from here.

All models use Pydantic v2 for validation and serialization.
"""

from pydantic import BaseModel, Field, field_validator

from slipp.constants import ProxyType
from slipp.models.caddy import CaddyConfig
from slipp.models.host import AnsibleHost
from slipp.models.service import LenientRuntime, Runtime
from slipp.models.types import PathStr
from slipp.utils.errors import HostNotFoundError
from slipp.utils.identifiers import validate_config_name


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
    """

    name: str
    framework: str
    path: PathStr
    port: int
    template_url: str
    dependencies: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """Directory names become systemd units/paths/YAML -- see validator."""
        return validate_config_name(value, "service name")


class DeploymentHostConfig(AnsibleHost):
    """Deployment host configuration extending AnsibleHost.

    Extends AnsibleHost with deployment-specific metadata for Ansible inventory.
    Inherits: inventory_hostname, ansible_host, ansible_user, ansible_port from AnsibleHost.

    Supports both slipp-native and external projects:
    - slipp projects: All fields populated
    - External projects (MDAD): app_domain and admin_email are None

    Attributes:
        app_domain: Domain for the application (used by Caddy). Optional for external projects.
        admin_email: Admin email for Let's Encrypt HTTPS certificates. Optional for external projects.
        runtime: How the app runs (systemd, docker, podman; default: docker)
        app_port: The primary service's own port. Only meaningful (and only
            needed in a URL) for --proxy none deploys, where nothing fronts
            the app on :80/:443 - set from the first detected service at
            launch time.
        proxy_owner: Cached result of ProxyResolutionStage's `--proxy auto`
            probe ("caddy" or "wg-manage"; None if never resolved or
            proxy was set explicitly). Persisted so re-launches/deploys
            against the same host skip the SSH probe.
    """

    app_domain: str | None = Field(default=None, description="Domain for app (Caddy)")
    admin_email: str | None = Field(
        default=None, description="Admin email for HTTPS certs"
    )
    runtime: LenientRuntime = Field(
        default=Runtime.DOCKER, description="How the app runs (systemd, docker, podman)"
    )
    app_port: int | None = Field(
        default=None, description="Primary service port (--proxy none deploys)"
    )
    proxy_owner: ProxyType | None = Field(
        default=None, description="Resolved --proxy auto owner: caddy or wg-manage"
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
        hosts = {}
        for name, config in hosts_data.items():
            # ansible_ssh_user is Ansible's own pre-2.0 alias for
            # ansible_user, still valid in hand-written inventories --
            # DeploymentHostConfig has no such field, so leaving it in
            # **config would be silently dropped by Pydantic and
            # ansible_user would default to root. from_ansible_inventory_json()
            # (below) already normalizes this; mirror it here for consistency.
            config = dict(config)
            ssh_user = config.pop("ansible_ssh_user", None)
            if ssh_user is not None:
                config.setdefault("ansible_user", ssh_user)
            hosts[name] = DeploymentHostConfig(inventory_hostname=name, **config)
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
                "hosts": {
                    # mode="json" so enum fields (e.g. runtime) dump as plain
                    # strings -- yaml.dump() has no representer for enum
                    # instances and would emit an unsafe !!python/object tag.
                    name: host.model_dump(mode="json")
                    for name, host in self.hosts.items()
                }
            }
        }

    @property
    def first_host(self) -> DeploymentHostConfig:
        """The first configured host, for single-host launch stages.

        Raises:
            HostNotFoundError: If hosts is empty (launch stages only call
                this after InventoryValidationStage has confirmed hosts
                exist).
        """
        try:
            return next(iter(self.hosts.values()))
        except StopIteration:
            raise HostNotFoundError("No hosts configured in inventory") from None


class ProvisionConfig(BaseModel):
    """Complete provisioning configuration for playbook generation.

    Combines all configuration needed to generate Ansible project.

    Attributes:
        services: Detected services
        inventory: Inventory configuration
        project_name: Project name
        project_root: Absolute path to project
        caddy_config: Caddy configuration
        skip_caddy: Skip Caddy role generation (for --proxy none/wg-manage)
        proxy: Reverse proxy mode (caddy, none, wg-manage)
    """

    services: list[DetectedService] = Field(description="Detected services")
    inventory: InventoryConfig = Field(description="Inventory configuration")
    project_name: str = Field(description="Project name")
    project_root: PathStr = Field(description="Absolute path to project")
    caddy_config: CaddyConfig = Field(description="Caddy configuration")
    skip_caddy: bool = Field(default=False, description="Skip Caddy role generation")
    proxy: ProxyType = Field(default=ProxyType.caddy, description="Reverse proxy mode")

    def to_dict(self) -> dict:
        """Convert to dict for template rendering.

        Returns:
            Dict with all fields formatted for Jinja2 templates
        """
        first_host = self.inventory.first_host

        return {
            "services": [s.model_dump() for s in self.services],
            "inventory": self.inventory.to_ansible_format(),
            "project_name": self.project_name,
            "project_root": str(self.project_root),
            "caddy_sites": [site.model_dump() for site in self.caddy_config.sites],
            "caddy_auto_https": self.caddy_config.auto_https,
            "caddy_sites_dir": self.caddy_config.sites_dir,
            "skip_caddy": self.skip_caddy,
            "proxy": self.proxy,
            "app_domain": first_host.app_domain or "",
            "runtime": first_host.runtime,
        }
