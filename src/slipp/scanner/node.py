"""Generic Node.js framework detector.

Detects Node.js projects by checking for package.json.
This is a fallback for Node.js projects without a specific framework detector.

Mirrors flyctl's node.go (simplified for MVP).
"""

from pathlib import Path

from slipp.scanner.helpers import (
    DEFAULT_NODE_PORT,
    NODE_DOCKER_TEMPLATE,
    extract_nodejs_dependencies,
    file_exists,
)
from slipp.scanner.models import SourceInfo


def configure_node(source_dir: Path) -> SourceInfo | None:
    """Configure generic Node.js application.

    Detects Node.js projects by checking for package.json.
    This is a fallback detector (runs after specific frameworks).

    Args:
        source_dir: Directory to scan.

    Returns:
        SourceInfo if Node.js project detected, None otherwise.

    Example:
        >>> info = configure_node(Path("/path/to/node-app"))
        >>> info.family
        'Node'
        >>> info.port
        3000
    """
    if not file_exists(source_dir, "package.json"):
        return None

    dependencies = extract_nodejs_dependencies(source_dir)

    return SourceInfo(
        family="Node",
        port=DEFAULT_NODE_PORT,
        template_url=NODE_DOCKER_TEMPLATE,
        dependencies=dependencies,
    )
