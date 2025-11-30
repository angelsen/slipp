"""Base class for variable extractors."""

from abc import ABC, abstractmethod
from typing import Any

from slipp.models.deployment import DetectedService


class VariableExtractor(ABC):
    """Base class for variable extraction strategies.

    Each language family (Python, Node.js, Go, etc.) implements this
    to extract template variables from DetectedService.
    """

    @abstractmethod
    def extract(self, service: DetectedService) -> dict[str, Any]:
        """Extract template variables for this language family.

        Args:
            service: Detected service from scanner

        Returns:
            Dictionary of template variables ready for rendering

        Example:
            >>> extractor = PythonVariableExtractor()
            >>> service = DetectedService(name="app", framework="flask", ...)
            >>> vars = extractor.extract(service)
            >>> vars["pythonVersion"]
            '3.12'
        """
        pass
