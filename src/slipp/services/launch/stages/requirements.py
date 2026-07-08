"""Ansible Galaxy requirements.yml generation stage."""

from pathlib import Path

from slipp.generator.requirements_generator import generate_requirements
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import FileGenerationStage, require


class RequirementsFileStage(FileGenerationStage[FullContext]):
    """Generate requirements.yml listing the Galaxy collections the project needs."""

    def __init__(self):
        super().__init__("Generating Galaxy requirements")

    def generate_content(self, context: FullContext) -> dict[Path, str]:
        """Generate requirements.yml content.

        Regeneration is skipped by the base class if the file exists and
        no longer carries the slipp generation marker.

        Args:
            context: Deployment context with inventory config.

        Returns:
            Dictionary mapping file path to content.
        """
        inventory_config = require(context.inventory_config, "inventory config")

        requirements_path = context.output_dir / "requirements.yml"
        first_host = inventory_config.first_host
        content = generate_requirements(first_host.runtime)

        return {requirements_path: content}
