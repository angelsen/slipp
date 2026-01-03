"""Generic Node.js framework detector.

Detects Node.js projects by checking for package.json with dependencies.
This is a fallback for Node.js projects without a specific framework detector.

Mirrors flyctl's node.go (simplified for MVP).
"""

from pathlib import Path

from slipp.scanner.helpers import extract_nodejs_dependencies
from slipp.scanner.models import ScannerConfig, SourceInfo

# Fly.io template URL (matches flyctl)
NODE_TEMPLATE = "https://raw.githubusercontent.com/superfly/flyctl/master/scanner/templates/node/Dockerfile"


def configure_node(
    source_dir: Path,
    config: ScannerConfig,
) -> SourceInfo | None:
    """Configure generic Node.js application.

    Detects Node.js projects by checking for package.json with dependencies.
    This is a fallback detector (runs after specific frameworks).

    Args:
        source_dir: Directory to scan.
        config: Scanner configuration (unused in MVP).

    Returns:
        SourceInfo if Node.js project detected, None otherwise.

    Example:
        >>> info = configure_node(Path("/path/to/node-app"), ScannerConfig())
        >>> info.family
        'Node'
        >>> info.port
        3000
    """
    dependencies = extract_nodejs_dependencies(source_dir)
    if not dependencies:
        return None

    return SourceInfo(
        family="Node",
        port=3000,
        template_url=NODE_TEMPLATE,
        dependencies=dependencies,
        env_vars={"PORT": "3000"},
    )
