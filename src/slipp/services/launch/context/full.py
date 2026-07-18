"""Full launch context for complete Ansible project generation."""

from dataclasses import dataclass, field
from pathlib import Path

from slipp.constants import DEFAULT_ENV, DEFAULT_SSH_PORT
from slipp.models.deployment import (
    DeploymentHostConfig,
    InventoryConfig,
    ProvisionConfig,
)
from slipp.models.local_config import ExposeEntry
from slipp.models.service import Runtime
from slipp.services.launch.context.scan import ScanContext
from slipp.utils.network import is_ip_address


@dataclass
class FullContext(ScanContext):
    """Context for full pipeline: scan codebase and generate Ansible project.

    Attributes:
        environment: Target environment name (e.g., 'dev', 'prod'). Only the
            full pipeline's inventory/registry stages read this.
        reconfigure: If True, regenerate existing configuration files.
        provision_config: Optional provisioning configuration.
        python_extra: uv sync --extra group name (Python systemd deploys).
        exec_args: Extra ExecStart arguments (Python systemd deploys).
        health_check: HTTP path polled after restart; rolls back to the
            previous deployment on failure (systemd deploys only).
        public: Expose via Let's Encrypt instead of internal CA
            (--proxy wg-manage only).
        expose: Resolved service routing (existing slipp.yaml block, or
            the seeded default) -- set lazily by resolve_expose(), then
            persisted by RegistrationStage.
        skip_caddy: If True, exclude Caddy proxy setup.
        host_ports: Resolved host-facing port per service name, set by
            PortResolutionStage. For container runtimes this is distinct
            from the service's own .port (its fixed internal listen port,
            baked unparameterized into the fetched Dockerfile template) --
            it's what the host-side `-p HOST:CONTAINER` publish, Caddy's
            reverse_proxy target, and wg-manage's service target all read.
            Empty until PortResolutionStage runs.
    """

    environment: str = DEFAULT_ENV
    reconfigure: bool = False
    provision_config: ProvisionConfig | None = None
    expose: dict[str, ExposeEntry] | None = None
    python_extra: str | None = None
    exec_args: str | None = None
    health_check: str | None = None
    public: bool = False
    skip_caddy: bool = False
    host_ports: dict[str, int] = field(default_factory=dict)


def build_context_for_provisioned_host(
    *,
    output_dir: Path,
    environment: str,
    project_name: str,
    ip: str,
    ssh_user: str,
    resolved_domain: str,
    public: bool = False,
) -> "FullContext":
    """FullContext for a host whose IP/domain slipp already resolved (`slipp up`).

    Skips the interactive inventory prompt that a bare `slipp launch` would
    otherwise need -- the caller has already provisioned or been given the
    host, and confirmed/registered the domain.
    """
    return FullContext(
        output_dir=output_dir,
        dry_run=False,
        environment=environment,
        project_dirs=[output_dir],
        project_name=project_name,
        public=public,
        inventory_config=InventoryConfig(
            hosts={
                environment: DeploymentHostConfig(
                    inventory_hostname=environment,
                    ansible_host=ip,
                    ansible_user=ssh_user,
                    ansible_port=DEFAULT_SSH_PORT,
                    app_domain=resolved_domain,
                    admin_email=None
                    if is_ip_address(resolved_domain)
                    else f"admin@{resolved_domain}",
                    runtime=Runtime.DOCKER,
                )
            }
        ),
    )
