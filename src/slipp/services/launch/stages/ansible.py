"""Ansible playbook, group_vars, and role file generation stages.

Provides stages for generating Ansible deployment artifacts including
the main playbook, group variables, and app role definitions.
"""

from pathlib import Path
from typing import Any

from slipp import output
from slipp.generator.env import make_env
from slipp.generator.playbook_generator import PlaybookGenerator
from slipp.generator.role_generator import RoleGenerator
from slipp.services.launch.stages.common import FileGenerationStage


class PlaybookGenerationStage(FileGenerationStage):
    """Generate playbook.yml file from provisioning config.

    Attributes:
        generator: PlaybookGenerator instance for rendering playbook content.
    """

    def __init__(self, playbook_generator: PlaybookGenerator):
        super().__init__("Generating playbook.yml")
        self.generator = playbook_generator

    def generate_content(self, context: Any) -> dict[Path, str]:
        assert context.provision_config is not None, "Provision config must be set"

        playbook_content = self.generator.generate(context.provision_config)
        playbook_path = context.output_dir / "playbook.yml"

        return {playbook_path: playbook_content}


class GroupVarsStage(FileGenerationStage):
    """Generate group_vars/all.yml from provisioning config template.

    Renders the group_vars template with provision configuration data.
    """

    def __init__(self):
        super().__init__("Generating group_vars/all.yml")

    def generate_content(self, context: Any) -> dict[Path, str]:
        assert context.provision_config is not None, "Provision config must be set"

        template = make_env().get_template("group_vars/all.yml.j2")
        group_vars_content = template.render(**context.provision_config.to_dict())

        group_vars_dir = context.output_dir / "group_vars"
        group_vars_path = group_vars_dir / "all.yml"

        return {group_vars_path: group_vars_content}


class AppRolesStage(FileGenerationStage):
    """Generate app role files for all services.

    Creates role definitions for each service in the deployment,
    determining role structure based on the container runtime.
    Continues on role generation errors to process remaining services.
    """

    def __init__(self):
        super().__init__("Generating app roles")

    def generate_content(self, context: Any) -> dict[Path, str]:
        assert context.inventory_config is not None, "Inventory config must be loaded"

        first_host = list(context.inventory_config.hosts.values())[0]
        runtime = first_host.container_runtime
        role_generator = RoleGenerator()

        all_files = {}
        for service in context.services:
            try:
                role_files = role_generator.generate_app_role(
                    service, context.project_name, runtime
                )

                for path, content in role_files.items():
                    all_files[context.output_dir / path] = content

            except Exception as e:
                output.error(f"Failed to generate role for {service.name}: {e}")
                continue

        return all_files
