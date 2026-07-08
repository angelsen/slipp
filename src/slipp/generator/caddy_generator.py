"""Caddy role generator for reverse proxy configuration."""

from pathlib import Path

from slipp.generator.env import render_template
from slipp.models.deployment import CaddyConfig


class CaddyGenerator:
    """Generate Caddy role for reverse proxy.

    Creates:
    - roles/caddy/tasks/main.yml (install Caddy, setup sites directory)
    - roles/caddy/templates/Caddyfile.j2 (main config with global options)
    - roles/caddy/templates/site.caddy.j2 (per-app config)
    - roles/caddy/handlers/main.yml (reload handler)
    - roles/caddy/defaults/main.yml (Caddy variables)

    Example:
        >>> config = CaddyConfig(sites=[...], auto_https=True)
        >>> generator = CaddyGenerator()
        >>> files = generator.generate(config)
    """

    def generate(
        self, config: CaddyConfig, project_name: str, app_domain: str, admin_email: str
    ) -> dict[Path, str]:
        """Generate Caddy role files.

        Args:
            config: Caddy configuration
            project_name: Project name for file naming
            app_domain: Application domain
            admin_email: Admin email for HTTPS certificates

        Returns:
            Dict mapping file paths to content

        Raises:
            TemplateGenerationError: If template rendering fails
        """
        return {
            Path("roles/caddy/tasks/main.yml"): self._render_tasks(
                config, project_name
            ),
            Path("roles/caddy/templates/Caddyfile.j2"): self._render_main_caddyfile(
                config, app_domain, admin_email
            ),
            Path("roles/caddy/templates/site.caddy.j2"): self._render_site_template(
                config, project_name
            ),
            Path("roles/caddy/handlers/main.yml"): self._render_handlers(),
            Path("roles/caddy/defaults/main.yml"): self._render_defaults(config),
        }

    def _render_tasks(self, config: CaddyConfig, project_name: str) -> str:
        """Render tasks/main.yml template."""
        return render_template(
            "roles/caddy/tasks/main.yml.j2",
            {"caddy_sites_dir": config.sites_dir, "project_name": project_name},
            label="Caddy tasks/main.yml",
        )

    def _render_main_caddyfile(
        self, config: CaddyConfig, app_domain: str, admin_email: str
    ) -> str:
        """Render templates/Caddyfile.j2 template."""
        return render_template(
            "roles/caddy/templates/Caddyfile.j2",
            {
                "admin_email": admin_email,
                "caddy_staging": config.staging,
                "caddy_sites_dir": config.sites_dir,
                "app_domain": app_domain,
            },
            label="Caddyfile.j2",
        )

    def _render_site_template(self, config: CaddyConfig, project_name: str) -> str:
        """Render templates/site.caddy.j2 template."""
        return render_template(
            "roles/caddy/templates/site.caddy.j2",
            {
                "caddy_sites": [site.model_dump() for site in config.sites],
                "project_name": project_name,
            },
            label="site.caddy.j2",
        )

    def _render_handlers(self) -> str:
        """Render handlers/main.yml template."""
        return render_template(
            "roles/caddy/handlers/main.yml.j2", {}, label="Caddy handlers/main.yml"
        )

    def _render_defaults(self, config: CaddyConfig) -> str:
        """Render defaults/main.yml template."""
        return render_template(
            "roles/caddy/defaults/main.yml.j2",
            {
                "caddy_auto_https": config.auto_https,
                "caddy_sites_dir": config.sites_dir,
                "caddy_staging": config.staging,
            },
            label="Caddy defaults/main.yml",
        )
