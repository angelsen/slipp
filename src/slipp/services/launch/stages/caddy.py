"""Caddy reverse proxy configuration stages for deployment."""

from pathlib import Path

from slipp import output
from slipp.utils.network import is_ip_address
from slipp.generator.caddy_generator import CaddyGenerator
from slipp.models.deployment import (
    CaddyConfig,
    CaddySite,
    DetectedService,
    ProvisionConfig,
)
from slipp.scanner.routing import classify_services
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import FileGenerationStage, require


def build_caddy_sites(services: list[DetectedService], domain: str) -> list[CaddySite]:
    """Build Caddy site configs based on detected services.

    Strategy:
    - Single service: domain → service
    - Multiple services: domain/api → backend, domain → frontend

    Args:
        services: List of detected services
        domain: Application domain

    Returns:
        List of CaddySite configurations
    """
    if len(services) == 1:
        return [
            CaddySite(domain=domain, upstream_port=services[0].port, path_prefix="/")
        ]

    roles = classify_services(services)

    sites = []
    if roles.backend:
        sites.append(
            CaddySite(
                domain=domain, upstream_port=roles.backend.port, path_prefix="/api"
            )
        )

    if roles.frontend:
        sites.append(
            CaddySite(domain=domain, upstream_port=roles.frontend.port, path_prefix="/")
        )

    # Add any remaining services as subdomains
    for service in roles.others:
        sites.append(
            CaddySite(
                domain=f"{service.name}.{domain}",
                upstream_port=service.port,
                path_prefix="/",
            )
        )

    return sites


class CaddyConfigStage:
    """Build Caddy reverse proxy configuration.

    Generates Caddy configuration from services and creates a
    ProvisionConfig with the resulting site mappings.
    """

    def execute(self, context: FullContext) -> None:
        """Execute the Caddy configuration stage.

        Builds Caddy sites from services and sets context.provision_config
        with the generated configuration.

        Args:
            context: Deployment context object with inventory_config, services,
                and skip_caddy flag.
        """
        inventory_config = require(context.inventory_config, "inventory config")

        first_host = inventory_config.first_host

        if not context.skip_caddy:
            output.info("Configuring Caddy reverse proxy...")

            app_domain = require(first_host.app_domain, "app_domain")
            is_ip = is_ip_address(app_domain)
            caddy_domain = ":80" if is_ip else app_domain

            caddy_sites = build_caddy_sites(context.services, caddy_domain)
            caddy_config = CaddyConfig(
                sites=caddy_sites,
                auto_https=not is_ip,
            )

            output.success(f"Configured {len(caddy_sites)} Caddy site(s)")
            output.list_items(
                [
                    f"{site.domain} → localhost:{site.upstream_port}"
                    for site in caddy_sites
                ],
                indent=4,
            )
        else:
            caddy_config = CaddyConfig(sites=[], auto_https=False)

        context.provision_config = ProvisionConfig(
            services=context.services,
            inventory=inventory_config,
            project_name=context.project_name,
            project_root=context.output_dir,
            caddy_config=caddy_config,
            skip_caddy=context.skip_caddy,
            proxy=context.proxy,
        )


class CaddyRoleStage(FileGenerationStage[FullContext]):
    """Generate Caddy role files.

    Creates Caddy role configuration files for Ansible deployment,
    including Caddyfile and supporting role structure.
    """

    def __init__(self):
        """Initialize Caddy role generation stage."""
        super().__init__("Generating Caddy role")

    def generate_content(self, context: FullContext) -> dict[Path, str]:
        """Generate Caddy role files.

        Args:
            context: Deployment context with provision_config and inventory_config.

        Returns:
            Mapping of file paths to generated content strings.
        """
        if context.skip_caddy:
            return {}

        inventory_config = require(context.inventory_config, "inventory config")
        provision_config = require(context.provision_config, "provision config")

        first_host = inventory_config.first_host

        app_domain = require(first_host.app_domain, "app_domain")
        admin_email = first_host.admin_email or ""
        if provision_config.caddy_config.auto_https:
            admin_email = require(first_host.admin_email, "admin_email")

        caddy_generator = CaddyGenerator()

        caddy_files = caddy_generator.generate(
            provision_config.caddy_config,
            context.project_name,
            app_domain,
            admin_email,
        )

        return {
            context.output_dir / path: content for path, content in caddy_files.items()
        }
