"""SvelteKit framework detector.

Detects SvelteKit applications by checking for @sveltejs/kit in dependencies.
Mirrors flyctl's jsFramework.go SvelteKit detection (lines 255-264).
"""

from pathlib import Path
from typing import Optional

from slipp.scanner.helpers import extract_nodejs_dependencies
from slipp.scanner.models import ScannerConfig, SourceInfo

# Fly.io template URL (matches flyctl)
SVELTEKIT_TEMPLATE = "https://raw.githubusercontent.com/superfly/flyctl/master/scanner/templates/node/Dockerfile"


def configure_sveltekit(
    source_dir: Path,
    config: ScannerConfig,
) -> Optional[SourceInfo]:
    """Configure SvelteKit application.

    Mirrors flyctl's SvelteKit detection (jsFramework.go lines 255-264).
    Extracts dependencies internally using language-specific helper.

    Detection:
    - Checks for @sveltejs/kit in Node.js dependencies (package.json)

    Args:
        source_dir: Directory to scan
        config: Scanner configuration (unused in MVP)

    Returns:
        SourceInfo if SvelteKit detected, None otherwise

    Example:
        >>> info = configure_sveltekit(Path("/path/to/sveltekit-app"), ScannerConfig())
        >>> info.family
        'SvelteKit'
        >>> info.port
        3000
    """
    # Extract Node.js dependencies using centralized helper
    dependencies = extract_nodejs_dependencies(source_dir)

    # Check for @sveltejs/kit (matches flyctl)
    if "@sveltejs/kit" not in dependencies:
        return None

    return SourceInfo(
        family="SvelteKit",
        port=3000,
        template_url=SVELTEKIT_TEMPLATE,
        dependencies=dependencies,
        env_vars={"PORT": "3000"},
    )
