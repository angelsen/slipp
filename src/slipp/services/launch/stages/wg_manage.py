"""wg-manage service exposure stage for deployment.

Alternative to CaddyRoleStage for targets where wg-manage already owns
Caddy (see roles/wg-manage-exposure) -- generates a role that shells out to
`wg-manage service add` per exposed service instead of templating a
Caddyfile directly.
"""

import shlex
from pathlib import Path

from slipp.constants import ProxyType
from slipp.generator.env import render_template
from slipp.services import wg_manage
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import (
    FileGenerationStage,
    require,
    resolve_expose,
)


class WgManageRoleStage(FileGenerationStage[FullContext]):
    """Generate the wg-manage-exposure role for --proxy wg-manage."""

    def __init__(self):
        """Initialize wg-manage role generation stage."""
        super().__init__("Generating wg-manage exposure role")

    def should_skip(self, context: FullContext) -> str | None:
        """Skip for any proxy other than wg-manage."""
        if context.proxy != ProxyType.wg_manage:
            return f"Skipping wg-manage exposure role (proxy: {context.proxy})"
        return None

    def generate_content(self, context: FullContext) -> dict[Path, str]:
        """Generate wg-manage-exposure role files.

        Args:
            context: Deployment context with inventory_config and services.

        Returns:
            Mapping of file paths to generated content strings.
        """
        inventory_config = require(context.inventory_config, "inventory config")
        app_domain = require(inventory_config.first_host.app_domain, "app_domain")

        expose = resolve_expose(context, app_domain)
        wg_services = wg_manage.build_wg_services(context.services, app_domain, expose)
        # fqdn/label are shell-quoted only for the generated command line --
        # build_wg_services()'s raw fqdn is also used by sync() for exact-string
        # comparison against wg-manage's stored service names, so it must not
        # be mutated here.
        services_ctx = [
            {**svc, "fqdn_quoted": shlex.quote(svc["fqdn"])} for svc in wg_services
        ]

        content = render_template(
            "roles/wg-manage-exposure/tasks/main.yml.j2",
            {
                "project_name": context.project_name,
                "wg_services": services_ctx,
                "public": context.public,
                "label": shlex.quote(wg_manage.service_label(context.project_name)),
            },
            label="wg-manage-exposure role",
        )

        return {context.output_dir / "roles/wg-manage-exposure/tasks/main.yml": content}
