"""Caddy role generator for reverse proxy configuration."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateError

from slipp.generator.errors import TemplateGenerationError
from slipp.models.deployment import CaddyConfig, CaddySite, DetectedService


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

    def __init__(self):
        """Initialize CaddyGenerator with Jinja2 environment."""
        # Find templates directory relative to this module
        template_dir = Path(__file__).parent / "templates"

        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

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
        files = {}

        try:
            # Render all Caddy role files
            files[Path("roles/caddy/tasks/main.yml")] = self._render_tasks(config)
            files[Path("roles/caddy/templates/Caddyfile.j2")] = (
                self._render_main_caddyfile(config, app_domain, admin_email)
            )
            files[Path("roles/caddy/templates/site.caddy.j2")] = (
                self._render_site_template(config, project_name)
            )
            files[Path("roles/caddy/handlers/main.yml")] = self._render_handlers()
            files[Path("roles/caddy/defaults/main.yml")] = self._render_defaults(config)

            return files
        except TemplateError as e:
            raise TemplateGenerationError(f"Failed to render Caddy role: {e}") from e
        except Exception as e:
            raise TemplateGenerationError(
                f"Unexpected error generating Caddy role: {e}"
            ) from e

    def _render_tasks(self, config: CaddyConfig) -> str:
        """Render tasks/main.yml template."""
        template = self.env.get_template("roles/caddy/tasks/main.yml.j2")
        return template.render(caddy_sites_dir=config.sites_dir)

    def _render_main_caddyfile(
        self, config: CaddyConfig, app_domain: str, admin_email: str
    ) -> str:
        """Render templates/Caddyfile.j2 template."""
        template = self.env.get_template("roles/caddy/templates/Caddyfile.j2")
        return template.render(
            admin_email=admin_email,
            caddy_staging=config.staging,
            caddy_sites_dir=config.sites_dir,
            app_domain=app_domain,
        )

    def _render_site_template(self, config: CaddyConfig, project_name: str) -> str:
        """Render templates/site.caddy.j2 template."""
        template = self.env.get_template("roles/caddy/templates/site.caddy.j2")
        return template.render(
            caddy_sites=[site.model_dump() for site in config.sites],
            project_name=project_name,
        )

    def _render_handlers(self) -> str:
        """Render handlers/main.yml template."""
        template = self.env.get_template("roles/caddy/handlers/main.yml.j2")
        return template.render()

    def _render_defaults(self, config: CaddyConfig) -> str:
        """Render defaults/main.yml template."""
        template = self.env.get_template("roles/caddy/defaults/main.yml.j2")
        return template.render(
            caddy_auto_https=config.auto_https,
            caddy_sites_dir=config.sites_dir,
            caddy_staging=config.staging,
            caddy_email=config.email,
        )

    @staticmethod
    def build_caddy_sites(
        services: list[DetectedService], domain: str
    ) -> list[CaddySite]:
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
                CaddySite(
                    domain=domain,
                    upstream_port=services[0].port,
                    path_prefix="/",
                )
            ]

        sites = []
        frontend = next(
            (s for s in services if s.framework in ["sveltekit", "nextjs", "gatsby"]),
            None,
        )
        backend = next(
            (s for s in services if s.framework in ["flask", "fastapi", "django"]),
            None,
        )

        if backend:
            sites.append(
                CaddySite(
                    domain=domain,
                    upstream_port=backend.port,
                    path_prefix="/api",
                )
            )

        if frontend:
            sites.append(
                CaddySite(
                    domain=domain,
                    upstream_port=frontend.port,
                    path_prefix="/",
                )
            )

        # Add any remaining services as subdomains
        for service in services:
            if service != frontend and service != backend:
                sites.append(
                    CaddySite(
                        domain=f"{service.name}.{domain}",
                        upstream_port=service.port,
                        path_prefix="/",
                    )
                )

        return sites
