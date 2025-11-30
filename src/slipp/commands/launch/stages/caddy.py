"""Caddy reverse proxy configuration stages for deployment.

This module provides stages for building and generating Caddy
configuration files during the launch/deployment process.
"""

from pathlib import Path
from typing import Any

from slipp import output
from slipp.generator.caddy_generator import CaddyGenerator
from slipp.models.deployment import CaddyConfig, ProvisionConfig

from .common import FileGenerationStage


class CaddyConfigStage:
    """Build Caddy reverse proxy configuration.

    Generates Caddy configuration from services and creates a
    ProvisionConfig with the resulting site mappings.
    """

    def execute(self, context: Any) -> None:
        """Execute the Caddy configuration stage.

        Builds Caddy sites from services and sets context.provision_config
        with the generated configuration.

        Args:
            context: Deployment context object with inventory_config, services,
                and skip_caddy flag.
        """
        assert context.inventory_config is not None, "Inventory config must be loaded"

        first_host = list(context.inventory_config.hosts.values())[0]

        if not context.skip_caddy:
            output.info("Configuring Caddy reverse proxy...")

            assert first_host.app_domain is not None, "app_domain must be set for Caddy"

            caddy_sites = CaddyGenerator.build_caddy_sites(
                context.services, first_host.app_domain
            )
            caddy_config = CaddyConfig(
                sites=caddy_sites,
                auto_https=True,
                staging=False,
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
            inventory=context.inventory_config,
            project_name=context.project_name,
            project_root=context.output_dir,
            caddy_config=caddy_config,
            skip_caddy=context.skip_caddy,
        )


class CaddyRoleStage(FileGenerationStage):
    """Generate Caddy role files.

    Creates Caddy role configuration files for Ansible deployment,
    including Caddyfile and supporting role structure.
    """

    def __init__(self):
        """Initialize Caddy role generation stage."""
        super().__init__("Generating Caddy role")

    def generate_content(self, context: Any) -> dict[Path, str]:
        """Generate Caddy role files.

        Args:
            context: Deployment context with provision_config and inventory_config.

        Returns:
            Mapping of file paths to generated content strings.
        """
        if context.skip_caddy:
            return {}

        assert context.inventory_config is not None, "Inventory config must be loaded"
        assert context.provision_config is not None, "Provision config must be set"

        first_host = list(context.inventory_config.hosts.values())[0]

        assert first_host.app_domain is not None, "app_domain must be set"
        assert first_host.admin_email is not None, "admin_email must be set"

        caddy_generator = CaddyGenerator()

        caddy_files = caddy_generator.generate(
            context.provision_config.caddy_config,
            context.project_name,
            first_host.app_domain,
            first_host.admin_email,
        )

        return {
            context.output_dir / path: content for path, content in caddy_files.items()
        }
