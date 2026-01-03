"""Scanner registry for framework detection.

Orchestrates framework detection by running detectors in priority order.
Mirrors flyctl's scanner.go Scan() function.
"""

from collections.abc import Callable
from pathlib import Path

from slipp.models.deployment import DetectedService
from slipp.scanner.flask import configure_flask
from slipp.scanner.models import ScannerConfig, SourceInfo
from slipp.scanner.node import configure_node
from slipp.scanner.python import configure_python
from slipp.scanner.sveltekit import configure_sveltekit

# Detectors must extract dependencies internally (not passed as arguments)
SourceScanner = Callable[[Path, ScannerConfig], SourceInfo | None]


def _source_info_to_detected_service(
    info: SourceInfo,
    path: Path,
    name: str,
) -> DetectedService:
    """Convert SourceInfo (internal) to DetectedService (public API).

    Args:
        info: Internal scanner result
        path: Path to service directory
        name: Service name (typically directory name)

    Returns:
        DetectedService for public API
    """
    return DetectedService(
        name=name,
        framework=info.family.lower(),  # Normalize to lowercase
        path=path,
        port=info.port,
        template_url=info.template_url,
        dependencies=info.dependencies,
        env_vars=info.env_vars,
    )


# Scanner registry in priority order (matches flyctl's scanner.go lines 115-140)
SCANNERS: list[SourceScanner] = [
    configure_flask,
    configure_sveltekit,
    configure_python,
    configure_node,
]


def scan(
    source_dir: Path, config: ScannerConfig | None = None
) -> DetectedService | None:
    """Scan directory for framework.

    Language-specific extraction architecture: Detectors call extraction
    functions internally when needed, eliminating centralized dependency
    passing and enabling per-language optimization.

    Process:
    1. Run framework detectors in priority order
    2. Each detector extracts dependencies using language-specific helpers
    3. First detector match wins, returns DetectedService

    Args:
        source_dir: Directory to scan
        config: Scanner configuration (optional, defaults to empty config)

    Returns:
        DetectedService if framework detected, None otherwise

    Example:
        >>> service = scan(Path("/path/to/flask-app"))
        >>> service.framework
        'flask'
    """
    if config is None:
        config = ScannerConfig()

    for scanner in SCANNERS:
        source_info = scanner(source_dir, config)
        if source_info is not None:
            return _source_info_to_detected_service(
                source_info, path=source_dir, name=source_dir.name
            )

    return None
