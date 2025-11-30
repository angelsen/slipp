"""Variable extractors for template rendering.

Strategy pattern for extracting template variables from DetectedService.
Mirrors the scanner's architecture with one extractor per language family.
"""

from typing import Any

from slipp.generator.extractors.base import VariableExtractor
from slipp.generator.extractors.nodejs_extractor import NodeJSVariableExtractor
from slipp.generator.extractors.python_extractor import PythonVariableExtractor
from slipp.models.deployment import DetectedService

# Registry: Maps framework name → extractor instance
# Mirrors scanner's SCANNERS list architecture
EXTRACTORS: dict[str, VariableExtractor] = {
    # Python frameworks (all use PythonVariableExtractor)
    "flask": PythonVariableExtractor(),
    "fastapi": PythonVariableExtractor(),
    "django": PythonVariableExtractor(),
    "python": PythonVariableExtractor(),
    # Node.js frameworks (all use NodeJSVariableExtractor)
    "sveltekit": NodeJSVariableExtractor(),
    "nextjs": NodeJSVariableExtractor(),
    "nuxtjs": NodeJSVariableExtractor(),
    "node": NodeJSVariableExtractor(),
}


def extract_template_variables(service: DetectedService) -> dict[str, Any]:
    """Extract template variables using registered extractor.

    Public API function that uses registry to find appropriate extractor.
    Mirrors scanner's scan() function architecture.

    Args:
        service: Detected service from scanner

    Returns:
        Dictionary of template variables ready for rendering

    Example:
        >>> from slipp.scanner import scan
        >>> from slipp.generator.extractors import extract_template_variables
        >>> service = scan(Path("examples/PoC/packages/backend"))
        >>> variables = extract_template_variables(service)
        >>> variables["flask"]
        True

    Raises:
        None - Falls back to minimal variables if no extractor registered
    """
    # Look up extractor in registry
    extractor = EXTRACTORS.get(service.framework)

    if extractor:
        return extractor.extract(service)

    # Fallback: minimal variables for unknown frameworks
    return {
        "appName": service.name,
        "port": service.port,
    }


__all__ = [
    "VariableExtractor",
    "PythonVariableExtractor",
    "NodeJSVariableExtractor",
    "EXTRACTORS",
    "extract_template_variables",
]
