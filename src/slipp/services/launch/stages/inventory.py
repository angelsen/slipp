"""Inventory-related stages."""

from pathlib import Path

import yaml

from slipp import output
from slipp.constants import (
    DEFAULT_SSH_PORT,
    DEFAULT_SSH_USER,
    ProxyType,
    get_inventory_filename,
)
from slipp.generator.template_generators import generate_inventory
from slipp.models.deployment import DeploymentHostConfig, InventoryConfig
from slipp.utils.network import is_ip_address
from slipp.models.service import Runtime
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import FileGenerationStage, require
from slipp.utils.errors import LaunchError
from slipp.services.launch.prompts import get_inventory_config


class InventoryLoadStage:
    """Load or prompt for inventory configuration."""

    def execute(self, context: FullContext) -> None:
        """Load inventory config from file or prompt user.

        Loads existing inventory if available and not reconfiguring,
        otherwise prompts user for configuration. In dry-run mode,
        creates dummy configuration. A caller that has already populated
        context.inventory_config (e.g. `slipp up` after provisioning a
        server via a provider API) short-circuits both the file load and
        the prompt.

        Args:
            context: Deployment context to populate with inventory config.
        """
        if context.inventory_config is not None:
            output.success("Using inventory pre-populated from provisioning")
        elif not context.dry_run:
            inventory_path = context.output_dir / get_inventory_filename(
                context.environment
            )

            if inventory_path.exists() and not context.reconfigure:
                output.success(
                    f"Using existing {get_inventory_filename(context.environment)}"
                )
                try:
                    with open(inventory_path) as f:
                        inventory_data = yaml.safe_load(f)
                    context.inventory_config = InventoryConfig.from_ansible_format(
                        inventory_data
                    )
                except Exception as e:
                    raise LaunchError(f"Failed to load {inventory_path}: {e}") from e
            else:
                context.inventory_config = get_inventory_config(context.environment)
        else:
            context.inventory_config = InventoryConfig(
                hosts={
                    context.environment: DeploymentHostConfig(
                        inventory_hostname=context.environment,
                        ansible_host="example.com",
                        ansible_user=DEFAULT_SSH_USER,
                        ansible_port=DEFAULT_SSH_PORT,
                        app_domain="example.com",
                        admin_email="admin@example.com",
                        runtime=Runtime.DOCKER,
                    )
                }
            )
            output.info(f"Dry run: Using dummy {context.environment} inventory config")

        # first_host.app_port and context.services[0].port need to agree
        # before any downstream stage (Caddy, wg-manage, compose, app
        # roles, InventoryFileStage) reads either one. Only the primary
        # service (index 0, the one app_port maps to) is eligible for this
        # - applying it to every service would clobber a secondary
        # service's own distinct port.
        first_host = context.inventory_config.first_host
        if not context.services:
            pass
        elif first_host.app_port is None:
            # No app_port yet (e.g. freshly scanned project) - adopt the
            # scanner's port guess.
            first_host.app_port = context.services[0].port
        elif first_host.app_port != context.services[0].port:
            # app_port is user-confirmed (or came from a hand-edited/
            # pre-existing inventory.yml) - it's authoritative.
            output.warning(
                f"Detected {context.services[0].name} now listening on "
                f"port {context.services[0].port}, but inventory.yml has "
                f"app_port={first_host.app_port} - keeping the persisted port"
            )
            output.hint(
                f"If the new port is correct, update app_port in inventory.yml "
                f"to {context.services[0].port}"
            )
            context.services[0] = context.services[0].model_copy(
                update={"port": first_host.app_port}
            )


class InventoryValidationStage:
    """Validate required deployment fields in inventory."""

    def execute(self, context: FullContext) -> None:
        """Validate that inventory has required fields for launch.

        Ensures inventory contains app_domain and admin_email which are
        required for the launch command. External projects should use
        'slipp deploy' with explicit inventory paths instead.

        Args:
            context: Deployment context with loaded inventory config.

        Raises:
            LaunchError: If required fields are missing.
        """
        inventory_config = require(
            context.inventory_config, "inventory config (before validation)"
        )

        first_host = inventory_config.first_host

        if not first_host.app_domain:
            raise LaunchError(
                "Launch command requires app_domain in inventory\n"
                "For external projects, use 'slipp deploy -i/-p' instead"
            )

        if not first_host.admin_email and not is_ip_address(first_host.app_domain):
            raise LaunchError(
                "Launch command requires admin_email in inventory\n"
                "For external projects, use 'slipp deploy -i/-p' instead"
            )

        # Unlike CaddyConfigStage (which falls back to routing an IP on
        # :80 with no subdomains), wg-manage has no IP-only mode --
        # build_wg_services() rejects it outright. Catching that here,
        # before any file-writing stage runs, avoids resolve_expose()
        # minting nonsense per-service subdomains (e.g. worker.1.2.3.4)
        # and failing mid-pipeline after inventory/playbook/group_vars
        # have already been written to disk.
        if context.proxy == ProxyType.wg_manage and is_ip_address(
            first_host.app_domain
        ):
            raise LaunchError(
                "wg-manage requires a real domain in app_domain -- "
                "IP-only targets aren't supported (wg-manage routes "
                "services via subdomains)"
            )


class InventoryFileStage(FileGenerationStage[FullContext]):
    """Generate inventory.yml file."""

    def __init__(self):
        super().__init__("Generating inventory file")

    def generate_content(self, context: FullContext) -> dict[Path, str]:
        """Generate inventory file content.

        Args:
            context: Deployment context with inventory config.

        Returns:
            Dictionary mapping file path to inventory YAML content.
        """
        inventory_config = require(context.inventory_config, "inventory config")

        inventory_filename = get_inventory_filename(context.environment)
        inventory_content = generate_inventory(inventory_config)
        inventory_path = context.output_dir / inventory_filename

        return {inventory_path: inventory_content}
