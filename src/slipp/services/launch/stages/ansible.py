"""Ansible playbook, group_vars, and role file generation stages.

Provides stages for generating Ansible deployment artifacts including
the main playbook, group variables, and app role definitions.
"""

from pathlib import Path

from slipp import output
from slipp.constants import PLAYBOOK_FILENAME
from slipp.generator.env import render_template
from slipp.generator.playbook_generator import generate_playbook
from slipp.generator.role_generator import extract_systemd_vars, generate_app_role
from slipp.models.service import Runtime
from slipp.scanner.models import PYTHON_FRAMEWORKS
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import FileGenerationStage, require


class PlaybookGenerationStage(FileGenerationStage[FullContext]):
    """Generate playbook.yml file from provisioning config."""

    def __init__(self):
        super().__init__("Generating playbook.yml")

    def generate_content(self, context: FullContext) -> dict[Path, str]:
        provision_config = require(context.provision_config, "provision config")

        playbook_content = generate_playbook(provision_config)
        playbook_path = context.output_dir / PLAYBOOK_FILENAME

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

        if context.health_check and runtime != Runtime.SYSTEMD:
            output.warning(
                f"--health-check {context.health_check} has no effect on "
                f"{runtime.value} deploys - health-check + rollback is only "
                "implemented for systemd."
            )

        any_python_systemd = runtime == Runtime.SYSTEMD and any(
            service.framework in PYTHON_FRAMEWORKS for service in context.services
        )
        for flag_name, flag_value in (
            ("exec-args", context.exec_args),
            ("python-extra", context.python_extra),
        ):
            if flag_value and not any_python_systemd:
                output.warning(
                    f"--{flag_name} has no effect on {runtime.value} deploys - "
                    "only used for Python systemd deploys."
                )

        all_files = {}
        for service in context.services:
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
            # Computed once here (not left to generate_app_role's own
            # internal call) so the missing-entrypoint check below and the
            # role generation itself share a single extract_template_variables()
            # call for this service.
            systemd_vars = (
                extract_systemd_vars(runtime, service) if is_python_systemd else None
            )
            if (
                is_python_systemd
                and not context.exec_args
                and systemd_vars
                and systemd_vars.get("execBinary") == "python"
                and not systemd_vars.get("execScript")
            ):
                output.warning(
                    f"{service.name} has no [project.scripts] entry and no "
                    "recognized entrypoint file (server.py/main.py/app.py/"
                    "run.py) - ExecStart would be a bare `python` with "
                    "nothing to run, which will crash-loop. Pass "
                    "--exec-args with the file/module to run, or add a "
                    "[project.scripts] entry."
                )
            role_files = generate_app_role(
                service,
                context.project_name,
                runtime,
                all_services=context.services,
                project_root=context.output_dir,
                uv_extra=context.python_extra,
                exec_args=context.exec_args,
                health_check=context.health_check,
                systemd_vars=systemd_vars,
            )

            for path, content in role_files.items():
                all_files[context.output_dir / path] = content

        return all_files
