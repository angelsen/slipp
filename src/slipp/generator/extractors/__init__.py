"""Variable extractors for template rendering.

One extraction function per language family, mirroring the scanner's
plain-function registry architecture (slipp.scanner.scanner).
"""

from collections.abc import Callable
from typing import Any

from slipp.generator.errors import GeneratorError
from slipp.generator.extractors.nodejs_extractor import extract_nodejs
from slipp.generator.extractors.python_extractor import extract_python
from slipp.models.deployment import DetectedService
from slipp.scanner.models import NODE_FRAMEWORKS, PYTHON_FRAMEWORKS

VariableExtractor = Callable[[DetectedService], dict[str, Any]]

# Registry: Maps framework name → extractor function. Built from the shared
# framework-family sets in slipp.scanner.models so it can't drift from what
# the scanner actually emits.
EXTRACTORS: dict[str, VariableExtractor] = {
    **{name: extract_python for name in PYTHON_FRAMEWORKS},
    **{name: extract_nodejs for name in NODE_FRAMEWORKS},
}


def extract_template_variables(service: DetectedService) -> dict[str, Any]:
    """Extract template variables using registered extractor.

    Public API function that uses registry to find appropriate extractor.
    Mirrors scanner's scan() function architecture.

    Args:
        service: Detected service from scanner

    Returns:
        Dictionary of template variables ready for rendering

    Raises:
        GeneratorError: If no extractor is registered for the service's framework
    """
    extractor = EXTRACTORS.get(service.framework)

    if extractor is None:
        raise GeneratorError(f"No extractor for framework {service.framework!r}")

    return extractor(service)


__all__ = ["extract_template_variables"]
