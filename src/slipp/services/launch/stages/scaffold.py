"""Scaffold stages for existing Ansible projects."""

from typing import Any

import typer

from slipp import output
from slipp.output import format_path
from slipp.services.ansible import (
    check_roles_installed,
    get_host_group,
    install_requirements,
    syntax_check,
)
from slipp.services.registry import ProjectRegistry
from slipp.utils.errors import LaunchError


class ScaffoldValidationStage:
    """Validate playbook exists and has valid syntax."""

    def execute(self, context: Any) -> None:
        """Verify playbook and install Ansible requirements."""
        output.task(f"Scaffolding inventory for {context.output_dir.name}")

        # Install requirements before validation (roles needed for syntax check)
        if context.requirements_path and context.requirements_path.exists():
            if not context.roles_path:
                raise LaunchError(
                    "--roles-path required when requirements.yml exists\n"
                    "Example: slipp generate scaffold -p setup.yml --roles-path roles/galaxy"
                )

            if check_roles_installed(context.roles_path):
                output.info(f"Roles already installed in {context.roles_path}")
            else:
                with output.spinner("Installing requirements") as update:
                    result = install_requirements(
                        str(context.requirements_path),
                        context.roles_path,
                        log_dir=output.get_log_dir(context.output_dir),
                        on_progress=update,
                    )
                if result.exit_code == 0:
                    output.success("Installing requirements")
                else:
                    message = "Installing requirements failed"
                    if result.log_path:
                        message += f"\nSee log: {result.log_path}"
                    raise LaunchError(message)

        if not context.playbook_path:
            raise LaunchError("No playbook specified")

        if not context.playbook_path.exists():
            raise LaunchError(
                f"Playbook not found: {format_path(context.playbook_path, context.output_dir)}"
            )

        output.info(
            f"Validating {format_path(context.playbook_path, context.output_dir)}..."
        )

        if not syntax_check(context.playbook_path):
            raise LaunchError(
                f"Playbook syntax check failed: {format_path(context.playbook_path, context.output_dir)}\n"
                f"Run: ansible-playbook --syntax-check "
                f"{format_path(context.playbook_path, context.output_dir)}"
            )

        output.success(
            f"Playbook valid: {format_path(context.playbook_path, context.output_dir)}"
        )

        context.host_group = get_host_group(context.playbook_path)
        output.info(f"Detected host group: {context.host_group}")


class ScaffoldPromptStage:
    """Prompt for inventory hostname and host IP."""

    def execute(self, context: Any) -> None:
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

    def execute(self, context: Any) -> None:
        """Create Ansible inventory structure with templated configuration files."""
        output.info("Generating inventory files...")

        if context.dry_run:
            output.info("Would generate: hosts file, vars.yml, vault.yml")
            return

        assert context.inventory_dir is not None

        context.inventory_dir.mkdir(parents=True, exist_ok=True)
        inventory_dir = context.output_dir / "inventory"
        inventory_dir.mkdir(parents=True, exist_ok=True)

        hosts_path = inventory_dir / "hosts"
        host_group = getattr(context, "host_group", "servers")
        hosts_content = f"""[{host_group}]
{context.hostname} ansible_host={context.host_ip} ansible_user=slipp ansible_become=true ansible_become_user=root
"""
        hosts_path.write_text(hosts_content)
        output.list_items(
            [str(hosts_path.relative_to(context.output_dir))], bullet=output.ICON_CHECK
        )
        context.generated_files.append(hosts_path)

        vars_path = context.inventory_dir / "vars.yml"
        vars_content = """---
# Add your host variables here
# Reference vault secrets with: "{{ vault_secret_name }}"
"""
        vars_path.write_text(vars_content)
        output.list_items(
            [str(vars_path.relative_to(context.output_dir))], bullet=output.ICON_CHECK
        )
        context.generated_files.append(vars_path)

        vault_path = context.inventory_dir / "vault.yml"
        vault_path.write_text("---\n# Add secrets with: slipp secrets add <name>\n")
        output.list_items(
            [str(vault_path.relative_to(context.output_dir))], bullet=output.ICON_CHECK
        )
        context.generated_files.append(vault_path)


class ScaffoldRegistrationStage:
    """Write local config and register project in global registry."""

    def execute(self, context: Any) -> None:
        """Create slipp.yaml and register project globally, with graceful error handling."""
        if context.dry_run:
            output.info("Dry run: would register project")
            return

        assert context.inventory_dir is not None

        from slipp.services.config import LocalConfigService

        try:
            LocalConfigService.create(
                name=context.project_name,
                inventory_path="inventory/hosts",
                playbook_path=str(
                    context.playbook_path.relative_to(context.output_dir)
                ),
                vault_path=str(
                    context.inventory_dir.relative_to(context.output_dir) / "vault.yml"
                ),
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


class ScaffoldSummaryStage:
    """Display summary and next steps."""

    def execute(self, context: Any) -> None:
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
