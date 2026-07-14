"""Docker Compose template context model with Pydantic v2 validation."""

from pathlib import Path

from pydantic import BaseModel, Field

from slipp.models.deployment import DetectedService
from slipp.models.types import PathStr


class ComposeConfig(BaseModel):
    """Context for docker-compose.yml template rendering.

    Attributes:
        services: Detected services
        project_name: Project name
        project_root: Project root directory for path relativization
    """

    services: list[DetectedService] = Field(description="Detected services")
    project_name: str = Field(description="Project name")
    project_root: PathStr = Field(description="Project root directory")

    def to_dict(self) -> dict:
        """Convert to dict for Jinja2 template context."""
        root = Path(self.project_root)
        services = []
        for s in self.services:
            data = s.model_dump()
            try:
                rel = Path(data["path"]).relative_to(root)
                data["build_context"] = "." if str(rel) == "." else f"./{rel}"
            except ValueError:
                # Service outside project_root (e.g. --dir pointed elsewhere)
                # -- fall back to an absolute context path.
                data["build_context"] = data["path"]
            services.append(data)

        return {
            "services": services,
            "project_name": self.project_name,
            "project_root": str(self.project_root),
        }
