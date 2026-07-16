"""Registration and summary stages."""

from slipp import output
from slipp.constants import ProxyType, get_inventory_filename
from slipp.models.service import Runtime
from slipp.services.launch.context import FullContext
from slipp.services.launch.registration import register_project
from slipp.services.launch.stages.common import (
    relative_or_absolute,
    require,
    skip_if_dry_run,
)
from slipp.utils.network import format_app_url


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
        if skip_if_dry_run(context, "register project"):
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
            roles_path=["roles"],
            project_dirs=[
                relative_or_absolute(d, context.output_dir)
                for d in context.project_dirs
            ],
            # Persists the resolved routing so it's visible/editable config
            # rather than an implicit convention (and so resources sync
            # prunes against the user's routing, not a re-derived default).
            # None for IP-only deploys, where no expose block is resolved.
            expose=context.expose,
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
                summary_items.append("roles/caddy/ (4 files)")
            elif context.proxy == ProxyType.wg_manage:
                summary_items.append("roles/wg-manage-exposure/ (1 file)")
            first_role_dir = f"roles/app-{context.services[0].name}/"
            files_per_service = sum(
                1
                for f in context.generated_files
                if relative_or_absolute(f, context.output_dir).startswith(
                    first_role_dir
                )
            )
            summary_items.append(
                f"roles/app-{{service}}/ ({len(context.services)} services, "
                f"{files_per_service} files each)"
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
                url = format_app_url(
                    first_host.app_domain,
                    has_caddy=not context.skip_caddy,
                    port=first_host.app_port,
                )
                output.stdout(f"  {url}")
