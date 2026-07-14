"""Generic Python framework detector.

Detects Python projects with priority-based detection for modern tooling.
Enhanced version: uv → Poetry → PEP 621 → Pipenv → pip (supersedes flyctl).

Mirrors and extends flyctl's python.go patterns.
"""

from pathlib import Path

from slipp.scanner.helpers import (
    DEFAULT_PYTHON_PORT,
    PYTHON_DOCKER_TEMPLATE,
    configure_by_dependency,
    detect_python_dep_manager,
    extract_python_dependencies,
    file_exists,
)
from slipp.scanner.models import SourceInfo


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
    is_python_project = detect_python_dep_manager(
        source_dir
    ) is not None or file_exists(source_dir, "setup.py", "setup.cfg", "environment.yml")
    if not is_python_project:
        return None

    return configure_by_dependency(
        source_dir,
        extract_python_dependencies,
        None,
        family="Python",
        port=DEFAULT_PYTHON_PORT,
        template_url=PYTHON_DOCKER_TEMPLATE,
    )
