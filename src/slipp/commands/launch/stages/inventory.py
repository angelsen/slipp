"""Inventory-related stages."""

from pathlib import Path
from typing import Any

import typer
import yaml

from slipp import output
from slipp.constants import get_inventory_filename
from slipp.generator.inventory_generator import InventoryGenerator
from slipp.models.deployment import DeploymentHostConfig, InventoryConfig
from slipp.utils.prompts import get_inventory_config

from .common import FileGenerationStage


class InventoryLoadStage:
    """Load or prompt for inventory configuration."""

    def execute(self, context: Any) -> None:
        """Load inventory config from file or prompt user."""
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
                        container_runtime="docker",
                    )
                }
            )
            output.info(f"Dry run: Using dummy {context.environment} inventory config")


class InventoryValidationStage:
    """Validate required deployment fields in inventory."""

    def execute(self, context: Any) -> None:
        """Validate that inventory has required fields for launch."""
        assert context.inventory_config is not None, (
            "Inventory config must be loaded before validation"
        )

        first_host = list(context.inventory_config.hosts.values())[0]

        if not first_host.app_domain:
            output.error("Launch command requires app_domain in inventory")
            output.error("For external projects, use 'ac deploy -i/-p' instead")
            raise typer.Exit(1)

        if not first_host.admin_email:
            output.error("Launch command requires admin_email in inventory")
            output.error("For external projects, use 'ac deploy -i/-p' instead")
            raise typer.Exit(1)


class InventoryFileStage(FileGenerationStage):
    """Generate inventory.yml file."""

    def __init__(self, inventory_generator: InventoryGenerator):
        """Initialize with inventory generator.

        Args:
            inventory_generator: Generator for creating inventory content.
        """
        super().__init__("Generating inventory file")
        self.generator = inventory_generator

    def generate_content(self, context: Any) -> dict[Path, str]:
        """Generate inventory file content.

        Args:
            context: Deployment context with inventory config.

        Returns:
            Dictionary mapping file path to inventory YAML content.
        """
        assert context.inventory_config is not None, "Inventory config must be loaded"

        inventory_filename = get_inventory_filename(context.environment)
        inventory_content = self.generator.generate(context.inventory_config)
        inventory_path = context.output_dir / inventory_filename

        return {inventory_path: inventory_content}
