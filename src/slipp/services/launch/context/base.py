"""Base context shared by all launch modes."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BaseContext:
    """Common fields shared by all launch contexts.

    Attributes:
        output_dir: Directory where generated artifacts are written.
        environment: Target environment name (e.g., 'dev', 'prod').
        dry_run: If True, do not write files or perform side effects.
        project_name: Name of the project being deployed.
        generated_files: List of paths to files generated during execution.
    """

    output_dir: Path
    environment: str
    dry_run: bool
    project_name: str = ""
    generated_files: list[Path] = field(default_factory=list)
