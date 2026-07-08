"""Inventory-related stages."""

from pathlib import Path

import yaml

from slipp import output
from slipp.constants import get_inventory_filename
from slipp.generator.inventory_generator import generate_inventory
from slipp.models.deployment import DeploymentHostConfig, InventoryConfig
from slipp.models.service import Runtime
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import FileGenerationStage
from slipp.utils.errors import LaunchError
from slipp.utils.prompts import get_inventory_config


class InventoryLoadStage:
    """Load or prompt for inventory configuration."""

    def execute(self, context: FullContext) -> None:
        """Load inventory config from file or prompt user.

        Loads existing inventory if available and not reconfiguring,
        otherwise prompts user for configuration. In dry-run mode,
        creates dummy configuration.

        Args:
            context: Deployment context to populate with inventory config.
        """
        if not context.dry_run:
            inventory_path = context.output_dir / get_inventory_filename(
                context.environment
            )

            if inventory_path.exists() and not context.reconfigure:
                output.success(
                    f"Using existing {get_inventory_filename(context.environment)}"
                )
                with open(inventory_path) as f:
                    inventory_data = yaml.safe_load(f)
                context.inventory_config = InventoryConfig.from_ansible_format(
                    inventory_data
                )
            else:
                context.inventory_config = get_inventory_config(
                    context.environment, context.reconfigure
                )
        else:
            context.inventory_config = InventoryConfig(
                hosts={
                    context.environment: DeploymentHostConfig(
                        name=context.environment,
                        inventory_hostname=context.environment,
                        ansible_host="example.com",
                        ansible_user="root",
                        ansible_port=22,
                        app_domain="example.com",
                        admin_email="admin@example.com",
                        runtime=Runtime.DOCKER,
                    )
                }
            )
            output.info(f"Dry run: Using dummy {context.environment} inventory config")


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
        assert context.inventory_config is not None, (
            "Inventory config must be loaded before validation"
        )

        first_host = context.inventory_config.first_host

        if not first_host.app_domain:
            raise LaunchError(
                "Launch command requires app_domain in inventory\n"
                "For external projects, use 'slipp deploy -i/-p' instead"
            )

        if not first_host.admin_email:
            raise LaunchError(
                "Launch command requires admin_email in inventory\n"
                "For external projects, use 'slipp deploy -i/-p' instead"
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
        assert context.inventory_config is not None, "Inventory config must be loaded"

        inventory_filename = get_inventory_filename(context.environment)
        inventory_content = generate_inventory(context.inventory_config)
        inventory_path = context.output_dir / inventory_filename

        return {inventory_path: inventory_content}
