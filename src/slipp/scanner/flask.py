"""Flask framework detector.

Detects Flask applications by checking for "flask" in Python dependencies.
Extracts dependencies internally using language-specific helper.
"""

from pathlib import Path

from slipp.scanner.helpers import (
    DEFAULT_PYTHON_PORT,
    PYTHON_DOCKER_TEMPLATE,
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
    dependencies = extract_python_dependencies(source_dir)
    if "flask" not in dependencies:
        return None

    return SourceInfo(
        family="Flask",
        port=DEFAULT_PYTHON_PORT,
        template_url=PYTHON_DOCKER_TEMPLATE,
        dependencies=dependencies,  # Include for metadata
    )
