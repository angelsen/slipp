"""SvelteKit framework detector.

Detects SvelteKit applications by checking for @sveltejs/kit in dependencies.
Mirrors flyctl's jsFramework.go SvelteKit detection (lines 255-264).
"""

from pathlib import Path

from slipp.scanner.helpers import (
    DEFAULT_NODE_PORT,
    NODE_DOCKER_TEMPLATE,
    configure_by_dependency,
    extract_nodejs_dependencies,
)
from slipp.scanner.models import SourceInfo


def configure_sveltekit(source_dir: Path) -> SourceInfo | None:
    """Configure SvelteKit application.

    Mirrors flyctl's SvelteKit detection (jsFramework.go lines 255-264).
    Extracts dependencies internally using language-specific helper.

    Detection:
    - Checks for @sveltejs/kit in Node.js dependencies (package.json)

    Args:
        source_dir: Directory to scan

    Returns:
        SourceInfo if SvelteKit detected, None otherwise

    Example:
        >>> info = configure_sveltekit(Path("/path/to/sveltekit-app"))
        >>> info.family
        'SvelteKit'
        >>> info.port
        3000
    """
    return configure_by_dependency(
        source_dir,
        extract_nodejs_dependencies,
        "@sveltejs/kit",
        family="SvelteKit",
        port=DEFAULT_NODE_PORT,
        template_url=NODE_DOCKER_TEMPLATE,
    )
