"""wg-manage service exposure stage for deployment.

Alternative to CaddyRoleStage for targets where wg-manage already owns
Caddy (see roles/wg-manage-exposure) -- generates a role that shells out to
`wg-manage service add` per exposed service instead of templating a
Caddyfile directly.
"""

from pathlib import Path

from slipp.generator.env import render_template
from slipp.models.deployment import DetectedService
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import FileGenerationStage, require


def build_wg_services(services: list[DetectedService], domain: str) -> list[dict]:
    """Build wg-manage service exposure entries, one per detected service.

    Mirrors build_caddy_sites()'s single-service case (caddy.py): bare
    domain when there's exactly one service. FQDNs only match Caddy's
    convention in that case, though -- for multi-service, every service
    here gets its own `service.name.domain` subdomain, including the one
    Caddy would put on the bare domain (frontend, or the sole service if
    no frontend/backend split is detected). wg-manage is one-FQDN-to-one-
    target (no path-prefix multiplexing), so Caddy's domain/api vs domain/
    split doesn't carry over -- there's no bare-domain slot to reuse for a
    multi-service project.

    Args:
        services: Detected services to expose.
        domain: Application domain.

    Returns:
        List of {name, fqdn, port} dicts for template rendering.
    """
    if len(services) == 1:
        return [{"name": services[0].name, "fqdn": domain, "port": services[0].port}]

    return [
        {
            "name": service.name,
            "fqdn": f"{service.name}.{domain}",
            "port": service.port,
        }
        for service in services
    ]


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

        wg_services = build_wg_services(context.services, app_domain)

        content = render_template(
            "roles/wg-manage-exposure/tasks/main.yml.j2",
            {
                "project_name": context.project_name,
                "wg_services": wg_services,
                "public": context.public,
            },
            label="wg-manage-exposure role",
        )

        return {context.output_dir / "roles/wg-manage-exposure/tasks/main.yml": content}
