"""Ansible playbook, group_vars, and role file generation stages.

Provides stages for generating Ansible deployment artifacts including
the main playbook, group variables, and app role definitions.
"""

from pathlib import Path

from slipp import output
from slipp.generator.env import render_template
from slipp.generator.extractors import extract_template_variables
from slipp.generator.playbook_generator import generate_playbook
from slipp.generator.role_generator import RoleGenerator
from slipp.models.service import Runtime
from slipp.scanner.models import PYTHON_FRAMEWORKS
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import FileGenerationStage, require
from slipp.utils.errors import LaunchError


class PlaybookGenerationStage(FileGenerationStage[FullContext]):
    """Generate playbook.yml file from provisioning config."""

    def __init__(self):
        super().__init__("Generating playbook.yml")

    def generate_content(self, context: FullContext) -> dict[Path, str]:
        provision_config = require(context.provision_config, "provision config")

        playbook_content = generate_playbook(provision_config)
        playbook_path = context.output_dir / "playbook.yml"

        return {playbook_path: playbook_content}


class GroupVarsStage(FileGenerationStage[FullContext]):
    """Generate group_vars/all.yml from provisioning config template.

    Renders the group_vars template with provision configuration data.
    """

    def __init__(self):
        super().__init__("Generating group_vars/all.yml")

    def generate_content(self, context: FullContext) -> dict[Path, str]:
        provision_config = require(context.provision_config, "provision config")

        group_vars_content = render_template(
            "group_vars/all.yml.j2",
            provision_config.to_dict(),
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
        inventory_config = require(context.inventory_config, "inventory config")

        first_host = inventory_config.first_host
        runtime = first_host.runtime
        role_generator = RoleGenerator()

        if context.health_check and runtime != Runtime.SYSTEMD:
            output.warning(
                f"--health-check {context.health_check} has no effect on "
                f"{runtime.value} deploys - health-check + rollback is only "
                "implemented for systemd."
            )

        all_files = {}
        for index, service in enumerate(context.services):
            is_python_systemd = (
                runtime == Runtime.SYSTEMD and service.framework in PYTHON_FRAMEWORKS
            )
            if is_python_systemd and not (service.path / "uv.lock").exists():
                output.warning(
                    f"{service.name} has no uv.lock in its own directory - "
                    "uv sync will run unfrozen (resolves fresh on every "
                    "deploy). If this is a uv workspace member, its lockfile "
                    "lives at the workspace root instead; commit a "
                    "standalone uv.lock here for reproducible, frozen "
                    "deploys."
                )
            if is_python_systemd and not context.exec_args:
                exec_vars = extract_template_variables(service)
                if exec_vars.get("execBinary") == "python" and not exec_vars.get(
                    "execScript"
                ):
                    output.warning(
                        f"{service.name} has no [project.scripts] entry and no "
                        "recognized entrypoint file (server.py/main.py/app.py/"
                        "run.py) - ExecStart would be a bare `python` with "
                        "nothing to run, which will crash-loop. Pass "
                        "--exec-args with the file/module to run, or add a "
                        "[project.scripts] entry."
                    )
            # service.port is the scanner's initial guess; first_host.app_port
            # is the user-confirmed deploy port and may have been changed
            # since (e.g. a hand-edited/pre-existing inventory.yml). The
            # generated unit/container templates bind to app_port, so role
            # generation must use it, not the stale scanner guess. Only the
            # primary service (index 0, the one app_port was seeded from -
            # see InventoryFileStage) is eligible: applying it to every
            # service would clobber a secondary service's own distinct port,
            # producing two units that both bind app_port.
            role_service = service
            if (
                index == 0
                and first_host.app_port
                and first_host.app_port != service.port
            ):
                role_service = service.model_copy(update={"port": first_host.app_port})

            try:
                role_files = role_generator.generate_app_role(
                    role_service,
                    context.project_name,
                    runtime,
                    all_services=context.services,
                    project_root=context.output_dir,
                    uv_extra=context.python_extra,
                    exec_args=context.exec_args,
                    health_check=context.health_check,
                )
            except Exception as e:
                raise LaunchError(
                    f"Failed to generate role for {service.name}: {e}"
                ) from e

            for path, content in role_files.items():
                all_files[context.output_dir / path] = content

        return all_files
