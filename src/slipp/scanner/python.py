"""Generic Python framework detector.

Detects Python projects with priority-based detection for modern tooling.
Enhanced version: uv → Poetry → PEP 621 → Pipenv → pip (supersedes flyctl).

Mirrors and extends flyctl's python.go patterns.
"""

from pathlib import Path

from slipp.scanner.helpers import (
    checks_pass,
    detect_python_dep_manager,
    extract_python_dependencies,
    file_exists,
)
from slipp.scanner.models import SourceInfo

PYTHON_TEMPLATE = "https://raw.githubusercontent.com/superfly/flyctl/master/scanner/templates/python-docker/Dockerfile"


def configure_python(source_dir: Path) -> SourceInfo | None:
    """Configure generic Python application.

    Enhanced priority-based detection (supersedes flyctl with uv support):
    1. uv (NEW - modern package manager, ahead of flyctl)
    2. Poetry (matches flyctl)
    3. PEP 621 pyproject.toml (matches flyctl)
    4. Pipenv (matches flyctl)
    5. pip/requirements.txt (matches flyctl)
    6. Generic fallback (setup.py, setup.cfg, environment.yml)

    Extracts dependencies internally using language-specific helper.

    Args:
        source_dir: Directory to scan

    Returns:
        SourceInfo if Python project detected, None otherwise

    Example:
        >>> info = configure_python(Path("/path/to/python-app"))
        >>> info.family
        'Python'
        >>> info.port
        8080
    """
    if detect_python_dep_manager(source_dir) is not None:
        dependencies = extract_python_dependencies(source_dir)
        return SourceInfo(
            family="Python",
            port=8080,
            template_url=PYTHON_TEMPLATE,
            env_vars={"PORT": "8080"},
            dependencies=dependencies,
        )

    if checks_pass(
        source_dir,
        file_exists("setup.py", "setup.cfg", "environment.yml"),
    ):
        dependencies = extract_python_dependencies(source_dir)
        return SourceInfo(
            family="Python",
            port=8080,
            template_url=PYTHON_TEMPLATE,
            env_vars={"PORT": "8080"},
            dependencies=dependencies,
        )

    return None
