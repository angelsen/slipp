"""Registration and summary stages."""

from slipp import output
from slipp.constants import get_inventory_filename
from slipp.models.service import Runtime
from slipp.services.launch.context import FullContext
from slipp.services.launch.registration import register_project
from slipp.services.launch.stages.common import require
from slipp.utils.network import is_ip_address


class RegistrationStage:
    """Write local config and register project in global registry."""

    def execute(self, context: FullContext) -> None:
        """Execute registration stage.

        Writes local slipp.yaml config and registers the project
        in the global registry.

        Args:
            context: Launch context with project configuration.

        Raises:
            LaunchError: If config creation or registration fails.
        """
        if context.dry_run:
            return

        inventory_config = require(context.inventory_config, "inventory config")
        inventory_filename = get_inventory_filename(context.environment)
        first_host = inventory_config.first_host
        register_project(
            name=context.project_name,
            project_root=context.output_dir,
            inventory_path=inventory_filename,
            playbook_path="playbook.yml",
            runtime=first_host.runtime.value,
        )


class SummaryStage:
    """Display summary of generated files and next steps."""

    def execute(self, context: FullContext) -> None:
        """Execute summary stage.

        Displays generated files, next steps, and final app URL.

        Args:
            context: Launch context with generated files and inventory config.
        """
        inventory_config = require(context.inventory_config, "inventory config")

        first_host = inventory_config.first_host

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
            ]
            if not context.skip_caddy:
                summary_items.append("roles/caddy/ (5 files)")
            summary_items.append(
                f"roles/app-{{service}}/ ({len(context.services)} services, 3 files each)"
            )
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

            if first_host.app_domain:
                output.blank()
                output.stdout("Your app will be available at:")
                scheme = "http" if is_ip_address(first_host.app_domain) else "https"
                if context.skip_caddy and context.services:
                    port = context.services[0].port
                    output.stdout(f"  {scheme}://{first_host.app_domain}:{port}")
                else:
                    output.stdout(f"  {scheme}://{first_host.app_domain}")
