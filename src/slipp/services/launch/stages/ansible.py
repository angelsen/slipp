"""Ansible playbook, group_vars, and role file generation stages.

Provides stages for generating Ansible deployment artifacts including
the main playbook, group variables, and app role definitions.
"""

from pathlib import Path

from slipp import output
from slipp.constants import PLAYBOOK_FILENAME
from slipp.generator.template_generators import generate_group_vars, generate_playbook
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

        group_vars_content = generate_group_vars(provision_config)

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
        provision_config = require(context.provision_config, "provision config")
        # Each service's own assigned host determines its runtime -- a
        # single global inventory_config.primary_host.runtime read (today's
        # only case, still what a single-host project resolves to) would
        # silently apply the wrong runtime to a service on a secondary host
        # with a different runtime.
        hosts_with_services = provision_config.hosts_with_services()

        any_systemd_with_services = any(
            host.runtime == Runtime.SYSTEMD and services
            for _, host, services in hosts_with_services
        )
        if context.health_check and not any_systemd_with_services:
            output.warning(
                f"--health-check {context.health_check} has no effect - "
                "health-check + rollback is only implemented for systemd, "
                "and no host in this deploy runs systemd."
            )

        any_python_systemd = any(
            host.runtime == Runtime.SYSTEMD and service.framework in PYTHON_FRAMEWORKS
            for _, host, services in hosts_with_services
            for service in services
        )
        for flag_name, flag_value in (
            ("exec-args", context.exec_args),
            ("python-extra", context.python_extra),
        ):
            if flag_value and not any_python_systemd:
                output.warning(
                    f"--{flag_name} has no effect - only used for Python "
                    "systemd deploys, and none of this deploy's services "
                    "are both."
                )

        all_files = {}
        for _host_name, host, services in hosts_with_services:
            runtime = host.runtime
            for service in services:
                is_python_systemd = (
                    runtime == Runtime.SYSTEMD
                    and service.framework in PYTHON_FRAMEWORKS
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
                # internal call) so the missing-entrypoint check below and
                # the role generation itself share a single
                # extract_template_variables() call for this service.
                systemd_vars = (
                    extract_systemd_vars(runtime, service)
                    if is_python_systemd
                    else None
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
                    host_port=context.host_ports.get(service.name, service.port),
                )

                for path, content in role_files.items():
                    all_files[context.output_dir / path] = content

        return all_files
