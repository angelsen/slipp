"""Deployment topology models: detected services, hosts, and inventory.

Caddy-specific config lives in models/caddy.py, compose template context in
models/compose.py -- both import DetectedService/ProvisionConfig from here.

All models use Pydantic v2 for validation and serialization.
"""

from pydantic import BaseModel, Field, field_validator

from slipp.constants import DEFAULT_SSH_PORT, DEFAULT_SSH_USER, ProxyType
from slipp.models.caddy import CaddyConfig
from slipp.models.host import AnsibleHost
from slipp.models.local_config import ExposeEntry, resolve_service_host
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
        is_primary: Whether this host owns the project's public identity
            (domain, proxy, DNS, admin email). Exactly one host in an
            InventoryConfig must have this set -- validated by
            InventoryConfig.primary_host, never inferred from dict/YAML
            ordering. Defaults True so a single-host project (today's only
            supported shape) needs no config change at all. `slipp hosts
            add` sets this False explicitly on every secondary host it
            creates.
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
    is_primary: bool = Field(
        default=True,
        description="Owns the project's public identity (domain/proxy/DNS)",
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
            # The dict key IS the host's identity -- an inventory_hostname
            # entry inside the per-host vars (as to_ansible_format()'s own
            # model_dump() writes, since it's a real DeploymentHostConfig
            # field) must never override or duplicate it. Popped rather
            # than asserted-equal: a hand-edited inventory.yml could
            # plausibly carry a stale one from a copy-paste, and the dict
            # key is authoritative regardless.
            config.pop("inventory_hostname", None)
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
            user = (
                vars.get("ansible_user")
                or vars.get("ansible_ssh_user")
                or DEFAULT_SSH_USER
            )

            hosts[hostname] = DeploymentHostConfig(
                inventory_hostname=hostname,
                ansible_host=vars.get("ansible_host", hostname),
                ansible_user=user,
                ansible_port=vars.get("ansible_port", DEFAULT_SSH_PORT),
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
    def primary_host(self) -> DeploymentHostConfig:
        """The host that owns the project's public identity.

        Replaces the old order-dependent `first_host` -- primary is
        determined by an explicit `is_primary` flag, never by dict/YAML
        ordering (which is silently fragile: hand-editing inventory.yml
        and reordering hosts would previously flip which host is "first").

        Raises:
            HostNotFoundError: If hosts is empty, or if the count of hosts
                with is_primary=True isn't exactly one -- names the
                offending host names and count so the fix is obvious.
        """
        primaries = [h for h in self.hosts.values() if h.is_primary]
        if len(primaries) == 1:
            return primaries[0]
        if not self.hosts:
            raise HostNotFoundError("No hosts configured in inventory")
        names = ", ".join(h.inventory_hostname for h in primaries) or "none"
        raise HostNotFoundError(
            f"expected exactly one primary host, found {len(primaries)}: {names}"
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
        skip_caddy: Skip Caddy role generation (for --proxy none/wg-manage)
        proxy: Reverse proxy mode (caddy, none, wg-manage)
        expose: Declared service routing (service name -> domain/path/host),
            as hand-written in slipp.yaml -- used only for its `.host`
            field here (see hosts_with_services()); domain/path drive Caddy
            /wg-manage site generation elsewhere. None for a first-time
            launch with no expose: block yet.
    """

    services: list[DetectedService] = Field(description="Detected services")
    inventory: InventoryConfig = Field(description="Inventory configuration")
    project_name: str = Field(description="Project name")
    project_root: PathStr = Field(description="Absolute path to project")
    caddy_config: CaddyConfig = Field(description="Caddy configuration")
    skip_caddy: bool = Field(default=False, description="Skip Caddy role generation")
    proxy: ProxyType = Field(default=ProxyType.caddy, description="Reverse proxy mode")
    expose: dict[str, ExposeEntry] | None = Field(
        default=None, description="Declared service routing (for .host resolution)"
    )

    def hosts_with_services(
        self,
    ) -> list[tuple[str, DeploymentHostConfig, list[DetectedService]]]:
        """Partition services by their assigned host, in inventory order.

        A service resolves to expose[service.name].host, or the primary
        host when unset -- a single-host project's every service resolves
        to the (sole) primary host, unchanged from today. Only hosts that
        own >=1 service, or the primary host itself (which may still need
        a play for the proxy role alone, even with zero services of its
        own), are included -- a secondary host with zero services is
        already rejected earlier, by InventoryValidationStage's orphaned-
        host check, so it never reaches here.

        Returns:
            (host_name, host, services) tuples, one per host actually
            referenced by the project -- playbook.yml.j2 renders one play
            per entry.
        """
        primary_name = self.inventory.primary_host.inventory_hostname
        declared_expose = self.expose or {}

        by_host: dict[str, list[DetectedService]] = {}
        for service in self.services:
            host_name = resolve_service_host(
                service.name, declared_expose, primary_name
            )
            by_host.setdefault(host_name, []).append(service)

        return [
            (name, host, by_host.get(name, []))
            for name, host in self.inventory.hosts.items()
            if name == primary_name or name in by_host
        ]

    def _infra_roles_for(self, host: "DeploymentHostConfig") -> list[dict]:
        """Proxy/infra roles for one host's play -- only the primary host gets one.

        Exactly one host owns Caddy/wg-manage, per design: a non-primary
        host's play carries app roles only.
        """
        if not host.is_primary:
            return []
        if not self.skip_caddy:
            return [{"name": "caddy", "tags": ["provision", "caddy"]}]
        if self.proxy == ProxyType.wg_manage:
            return [{"name": "wg-manage-exposure", "tags": ["provision", "wg-manage"]}]
        return []

    def to_dict(self) -> dict:
        """Convert to dict for template rendering.

        Returns:
            Dict with all fields formatted for Jinja2 templates
        """
        primary_host = self.inventory.primary_host

        return {
            "services": [s.model_dump() for s in self.services],
            "project_name": self.project_name,
            "project_root": str(self.project_root),
            "caddy_auto_https": self.caddy_config.auto_https,
            "caddy_sites_dir": self.caddy_config.sites_dir,
            "skip_caddy": self.skip_caddy,
            "proxy": self.proxy,
            "app_domain": primary_host.app_domain or "",
            "runtime": primary_host.runtime,
            # Fully resolved per-play role list, computed here rather than
            # with proxy/skip_caddy conditionals in playbook.yml.j2 -- the
            # template just loops.
            "hosts_with_services": [
                {
                    "host_name": name,
                    "runtime": host.runtime,
                    "infra_roles": self._infra_roles_for(host),
                    "app_roles": [
                        {"name": f"app-{s.name}", "tags": ["deploy", s.name]}
                        for s in services
                    ],
                }
                for name, host, services in self.hosts_with_services()
            ],
        }
