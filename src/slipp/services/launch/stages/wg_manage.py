"""wg-manage service exposure stage for deployment.

Alternative to CaddyRoleStage for targets where wg-manage already owns
Caddy (see roles/wg-manage-exposure) -- generates a role that shells out to
`wg-manage service add` per exposed service instead of templating a
Caddyfile directly.
"""

from pathlib import Path

from slipp.generator.env import render_template
from slipp.services import wg_manage
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import FileGenerationStage, require


class WgManageRoleStage(FileGenerationStage[FullContext]):
    """Generate the wg-manage-exposure role for --proxy wg-manage."""

    def __init__(self):
        """Initialize wg-manage role generation stage."""
        super().__init__("Generating wg-manage exposure role")

    def generate_content(self, context: FullContext) -> dict[Path, str]:
        """Generate wg-manage-exposure role files.

        Args:
            context: Deployment context with inventory_config and services.

        Returns:
            Mapping of file paths to generated content strings.
        """
        if context.proxy != "wg-manage":
            return {}

        inventory_config = require(context.inventory_config, "inventory config")
        app_domain = require(inventory_config.first_host.app_domain, "app_domain")

        wg_services = wg_manage.build_wg_services(context.services, app_domain)

        content = render_template(
            "roles/wg-manage-exposure/tasks/main.yml.j2",
            {
                "project_name": context.project_name,
                "wg_services": wg_services,
                "public": context.public,
                "label": wg_manage.service_label(context.project_name),
            },
            label="wg-manage-exposure role",
        )

        return {context.output_dir / "roles/wg-manage-exposure/tasks/main.yml": content}
