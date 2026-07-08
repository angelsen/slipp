"""Ansible playbook, group_vars, and role file generation stages.

Provides stages for generating Ansible deployment artifacts including
the main playbook, group variables, and app role definitions.
"""

from pathlib import Path

from slipp.generator.env import render_template
from slipp.generator.playbook_generator import generate_playbook
from slipp.generator.role_generator import RoleGenerator
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import FileGenerationStage
from slipp.utils.errors import LaunchError


class PlaybookGenerationStage(FileGenerationStage[FullContext]):
    """Generate playbook.yml file from provisioning config."""

    def __init__(self):
        super().__init__("Generating playbook.yml")

    def generate_content(self, context: FullContext) -> dict[Path, str]:
        assert context.provision_config is not None, "Provision config must be set"

        playbook_content = generate_playbook(context.provision_config)
        playbook_path = context.output_dir / "playbook.yml"

        return {playbook_path: playbook_content}


class GroupVarsStage(FileGenerationStage[FullContext]):
    """Generate group_vars/all.yml from provisioning config template.

    Renders the group_vars template with provision configuration data.
    """

    def __init__(self):
        super().__init__("Generating group_vars/all.yml")

    def generate_content(self, context: FullContext) -> dict[Path, str]:
        assert context.provision_config is not None, "Provision config must be set"

        group_vars_content = render_template(
            "group_vars/all.yml.j2",
            context.provision_config.to_dict(),
            label="group_vars/all.yml",
        )

        group_vars_dir = context.output_dir / "group_vars"
        group_vars_path = group_vars_dir / "all.yml"

        return {group_vars_path: group_vars_content}


class AppRolesStage(FileGenerationStage[FullContext]):
    """Generate app role files for all services.

    Creates role definitions for each service in the deployment,
    determining role structure based on the runtime (systemd, docker, or
    podman).
    """

    def __init__(self):
        super().__init__("Generating app roles")

    def generate_content(self, context: FullContext) -> dict[Path, str]:
        assert context.inventory_config is not None, "Inventory config must be loaded"

        first_host = context.inventory_config.first_host
        runtime = first_host.runtime
        role_generator = RoleGenerator()

        all_files = {}
        for service in context.services:
            try:
                role_files = role_generator.generate_app_role(
                    service,
                    context.project_name,
                    runtime,
                    all_services=context.services,
                    project_root=context.output_dir,
                )
            except Exception as e:
                raise LaunchError(
                    f"Failed to generate role for {service.name}: {e}"
                ) from e

            for path, content in role_files.items():
                all_files[context.output_dir / path] = content

        return all_files
