"""Scaffold stages for existing Ansible projects."""

from pathlib import Path

import typer

from slipp import output
from slipp.output import format_path
from slipp.utils.files import get_log_dir
from slipp.services.ansible import (
    ensure_requirements_installed,
    get_host_group,
    syntax_check,
)
from slipp.services.launch.context import ScaffoldContext
from slipp.services.launch.registration import register_project
from slipp.services.launch.stages.common import require, write_generated_file
from slipp.utils.errors import LaunchError


class ScaffoldValidationStage:
    """Validate playbook exists and has valid syntax."""

    def execute(self, context: ScaffoldContext) -> None:
        """Verify playbook and install Ansible requirements."""
        output.task(f"Scaffolding inventory for {context.output_dir.name}")

        # Install requirements before validation (roles needed for syntax check)
        if context.requirements_path and context.requirements_path.exists():
            if not context.roles_path:
                raise LaunchError(
                    "--roles-path required when requirements.yml exists\n"
                    "Example: slipp generate scaffold -p setup.yml --roles-path roles/galaxy"
                )

            ensure_requirements_installed(
                str(context.requirements_path),
                context.roles_path,
                log_dir=get_log_dir(context.output_dir),
            )

        if not context.playbook_path:
            raise LaunchError("No playbook specified")

        if not context.playbook_path.exists():
            raise LaunchError(
                f"Playbook not found: {format_path(context.playbook_path, context.output_dir)}"
            )

        output.info(
            f"Validating {format_path(context.playbook_path, context.output_dir)}..."
        )

        roles = [context.roles_path] if context.roles_path else None

        if not syntax_check(context.playbook_path, roles_path=roles):
            raise LaunchError(
                f"Playbook syntax check failed: {format_path(context.playbook_path, context.output_dir)}\n"
                f"Run: ansible-playbook --syntax-check "
                f"{format_path(context.playbook_path, context.output_dir)}"
            )

        output.success(
            f"Playbook valid: {format_path(context.playbook_path, context.output_dir)}"
        )

        context.host_group = get_host_group(context.playbook_path, roles_path=roles)
        output.info(f"Detected host group: {context.host_group}")


class ScaffoldPromptStage:
    """Prompt for inventory hostname and host IP."""

    def execute(self, context: ScaffoldContext) -> None:
        """Collect hostname and IP from user or use dry-run placeholders."""
        if context.dry_run:
            context.hostname = "<hostname>"
            context.host_ip = "<ip>"
            context.inventory_dir = (
                context.output_dir / "inventory" / "host_vars" / "<hostname>"
            )
            output.info("Dry run: using placeholder values")
            return

        output.blank()

        context.hostname = typer.prompt("Inventory hostname")
        context.host_ip = typer.prompt("Host IP address")

        if context.inventory_path:
            inv_dir = context.inventory_path
            if inv_dir.suffix:
                inv_dir = inv_dir.parent
            context.inventory_dir = inv_dir
        else:
            context.inventory_dir = (
                context.output_dir / "inventory" / "host_vars" / context.hostname
            )

        output.success(
            f"Will create inventory at: {format_path(context.inventory_dir, context.output_dir)}"
        )


class ScaffoldInventoryStage:
    """Generate inventory files (hosts, vars.yml, vault.yml)."""

    def execute(self, context: ScaffoldContext) -> None:
        """Create Ansible inventory structure with templated configuration files."""
        output.info("Generating inventory files...")

        if context.dry_run:
            output.info("Would generate: hosts file, vars.yml, vault.yml")
            return

        host_inventory_dir = require(context.inventory_dir, "inventory dir")

        host_inventory_dir.mkdir(parents=True, exist_ok=True)
        inventory_dir = context.output_dir / "inventory"
        inventory_dir.mkdir(parents=True, exist_ok=True)

        hosts_content = f"""[{context.host_group}]
{context.hostname} ansible_host={context.host_ip} ansible_user=slipp ansible_become=true ansible_become_user=root
"""
        write_generated_file(
            inventory_dir / "hosts", hosts_content, context, never_overwrite=True
        )

        vars_content = """---
# Add your host variables here
# Reference vault secrets with: "{{ vault_secret_name }}"
"""
        write_generated_file(
            host_inventory_dir / "vars.yml",
            vars_content,
            context,
            never_overwrite=True,
        )

        vault_content = "---\n# Add secrets with: slipp secrets add <name>\n"
        write_generated_file(
            host_inventory_dir / "vault.yml",
            vault_content,
            context,
            never_overwrite=True,
        )


class ScaffoldRegistrationStage:
    """Write local config and register project in global registry."""

    def execute(self, context: ScaffoldContext) -> None:
        """Create slipp.yaml and register project globally.

        Raises LaunchError on failure (rather than warning and continuing)
        so a broken registration can't be masked by a false "Scaffold
        complete!" summary.
        """
        if context.dry_run:
            output.info(f"Dry run: would register project '{context.project_name}'")
            return

        host_inventory_dir = require(context.inventory_dir, "inventory dir")
        playbook_path = require(context.playbook_path, "playbook path")

        galaxy_path: str | None = None
        if context.roles_path:
            roles_path_obj = Path(context.roles_path)
            galaxy_path = (
                str(roles_path_obj.relative_to(context.output_dir))
                if roles_path_obj.is_absolute()
                else str(roles_path_obj)
            )

        register_project(
            name=context.project_name,
            project_root=context.output_dir,
            inventory_path="inventory/hosts",
            playbook_path=str(playbook_path.relative_to(context.output_dir)),
            galaxy_path=galaxy_path,
            vault_path=str(
                host_inventory_dir.relative_to(context.output_dir) / "vault.yml"
            ),
        )


class ScaffoldSummaryStage:
    """Display summary and next steps."""

    def execute(self, context: ScaffoldContext) -> None:
        """Print generated files and display post-scaffold instructions."""
        if context.dry_run:
            output.warning("Dry run complete (no files written)")
            return

        output.blank()
        output.success("Scaffold complete!")
        output.blank()

        output.stdout(f"Generated {len(context.generated_files)} files:")
        output.list_items(
            [str(f.relative_to(context.output_dir)) for f in context.generated_files],
            bullet=output.ICON_BULLET,
        )

        output.blank()
        output.stdout("Next steps:")
        output.list_items(
            [
                "Edit vars.yml with your configuration",
                "slipp secret add <secret_name>  # for each secret",
                "slipp deploy",
            ],
            numbered=True,
        )
