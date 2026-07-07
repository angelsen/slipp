"""Registration and summary stages."""

from typing import Any

from slipp import output
from slipp.constants import get_inventory_filename
from slipp.models.service import Runtime
from slipp.services.config import LocalConfigService
from slipp.services.registry import ProjectRegistry


class RegistrationStage:
    """Write local config and register project in global registry."""

    def execute(self, context: Any) -> None:
        """Execute registration stage.

        Writes local slipp.yaml config and registers the project
        in the global registry. Gracefully handles errors.

        Args:
            context: Launch context with project configuration.
        """
        if context.dry_run:
            return

        try:
            inventory_filename = get_inventory_filename(context.environment)
            first_host = list(context.inventory_config.hosts.values())[0]
            LocalConfigService.create(
                name=context.project_name,
                inventory_path=inventory_filename,
                playbook_path="playbook.yml",
                runtime=first_host.runtime.value,
                project_root=context.output_dir,
            )
            output.success(f"Created slipp.yaml with name '{context.project_name}'")
        except Exception as e:
            output.warning(f"Failed to create local config: {e}")

        try:
            ProjectRegistry().register(
                name=context.project_name,
                project_path=context.output_dir,
            )
            output.info(f"Registered '{context.project_name}' in global registry")
        except Exception as e:
            output.warning(f"Failed to register project: {e}")


class SummaryStage:
    """Display summary of generated files and next steps."""

    def execute(self, context: Any) -> None:
        """Execute summary stage.

        Displays generated files, next steps, and final app URL.

        Args:
            context: Launch context with generated files and inventory config.
        """
        assert context.inventory_config is not None, "Inventory config must be loaded"

        first_host = list(context.inventory_config.hosts.values())[0]

        if context.dry_run:
            output.warning("Dry run complete (no files written)")
            output.hint(
                "Would generate 20+ files including inventory, playbook, roles, and Dockerfiles"
            )
        else:
            is_systemd = first_host.runtime == Runtime.SYSTEMD

            output.success("Launch complete!")
            output.blank()
            output.stdout(f"Generated {len(context.generated_files)} files:")
            summary_items = [
                "inventory.yml",
                "playbook.yml",
                "group_vars/all.yml",
                "roles/caddy/ (5 files)",
                f"roles/app-{{service}}/ ({len(context.services)} services, 3 files each)",
            ]
            if not is_systemd:
                summary_items += [
                    f"Dockerfiles ({len(context.services)} services)",
                    "docker-compose.yml",
                ]
            output.list_items(summary_items)

            output.blank()
            output.stdout("Next steps:")
            next_steps = ["Review generated files"]
            if not is_systemd:
                next_steps.append("Test locally: docker compose up")
            next_steps.append("Deploy to VPS: slipp deploy")
            output.list_items(next_steps, numbered=True)

            output.blank()
            output.stdout("Your app will be available at:")
            output.stdout(f"  https://{first_host.app_domain}")
