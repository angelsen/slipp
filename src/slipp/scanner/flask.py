"""Flask framework detector.

Detects Flask applications by checking for "flask" in Python dependencies.
Extracts dependencies internally using language-specific helper.
"""

from pathlib import Path

from slipp.scanner.helpers import (
    DEFAULT_PYTHON_PORT,
    PYTHON_DOCKER_TEMPLATE,
    configure_by_dependency,
    extract_python_dependencies,
)
from slipp.scanner.models import SourceInfo


def configure_flask(source_dir: Path) -> SourceInfo | None:
    """Configure Flask application.

    Extracts Python dependencies internally and checks for "flask" package.

    Detection:
    - Calls extract_python_dependencies() to parse pyproject.toml, requirements.txt
    - Checks if "flask" is present in dependencies

    Args:
        source_dir: Directory to scan

    Returns:
        SourceInfo if Flask detected, None otherwise

    Example:
        >>> info = configure_flask(Path("/path/to/flask-app"))
        >>> info.family
        'Flask'
        >>> info.port
        8080
    """
    return configure_by_dependency(
        source_dir,
        extract_python_dependencies,
        "flask",
        family="Flask",
        port=DEFAULT_PYTHON_PORT,
        template_url=PYTHON_DOCKER_TEMPLATE,
    )
