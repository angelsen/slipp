"""Flask framework detector.

Detects Flask applications by checking for "flask" in Python dependencies.
Extracts dependencies internally using language-specific helper.
"""

from pathlib import Path
from typing import Optional

from slipp.scanner.helpers import extract_python_dependencies
from slipp.scanner.models import ScannerConfig, SourceInfo

# Fly.io template URL (matches flyctl)
FLASK_TEMPLATE = "https://raw.githubusercontent.com/superfly/flyctl/master/scanner/templates/python-docker/Dockerfile"


def configure_flask(
    source_dir: Path,
    config: ScannerConfig,
) -> Optional[SourceInfo]:
    """Configure Flask application.

    Extracts Python dependencies internally and checks for "flask" package.

    Detection:
    - Calls extract_python_dependencies() to parse pyproject.toml, requirements.txt
    - Checks if "flask" is present in dependencies

    Args:
        source_dir: Directory to scan
        config: Scanner configuration (unused in MVP)

    Returns:
        SourceInfo if Flask detected, None otherwise

    Example:
        >>> info = configure_flask(Path("/path/to/flask-app"), ScannerConfig())
        >>> info.family
        'Flask'
        >>> info.port
        8080
    """
    # Extract Python dependencies using centralized helper
    dependencies = extract_python_dependencies(source_dir)

    # Simple membership check
    if "flask" not in dependencies:
        return None

    return SourceInfo(
        family="Flask",
        port=8080,
        template_url=FLASK_TEMPLATE,
        env_vars={"PORT": "8080"},
        dependencies=dependencies,  # Include for metadata
    )
