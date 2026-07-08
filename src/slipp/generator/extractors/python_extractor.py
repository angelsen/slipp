"""Python variable extractor for template rendering.

Extracts template variables for all Python frameworks (Flask, FastAPI, Django, etc.).
"""

from pathlib import Path
from typing import Any

from slipp.generator.extractors.base import VariableExtractor
from slipp.models.deployment import DetectedService


class PythonVariableExtractor(VariableExtractor):
    """Extract template variables for Python frameworks.

    Handles all Python-based frameworks: Flask, FastAPI, Django, Streamlit, etc.
    Reusable across different Python frameworks since they share the same template variables.
    """

    def extract(self, service: DetectedService) -> dict[str, Any]:
        """Extract Python template variables from DetectedService.

        Args:
            service: Detected Python service

        Returns:
            Dictionary of Python template variables

        Example:
            >>> service = DetectedService(
            ...     name="backend",
            ...     framework="flask",
            ...     path=Path("examples/PoC/packages/backend"),
            ...     dependencies=["flask", "gunicorn"],
            ...     port=8080
            ... )
            >>> extractor = PythonVariableExtractor()
            >>> vars = extractor.extract(service)
            >>> vars["pythonVersion"]
            '3.12'
            >>> vars["flask"]
            True
        """
        variables = {}

        # Common variables
        variables["appName"] = service.name
        variables["port"] = service.port

        # Python version detection
        python_version = self._detect_python_version(service.path)
        variables["pythonVersion"] = python_version
        variables["pyVersion"] = python_version  # Alias for python-docker template

        # Dependency manager detection
        dep_manager = self._detect_dependency_manager(service.path)
        variables.update(dep_manager)

        # Framework detection (boolean flags)
        variables["flask"] = "flask" in service.dependencies
        variables["fastapi"] = "fastapi" in service.dependencies
        variables["django"] = "django" in service.dependencies
        variables["streamlit"] = "streamlit" in service.dependencies

        # Database detection
        variables["hasPostgres"] = any(
            "psycopg" in dep or "postgres" in dep for dep in service.dependencies
        )

        # Entrypoint detection (for streamlit)
        if variables["streamlit"]:
            variables["entrypoint"] = self._find_streamlit_entrypoint(service.path)

        return variables

    def _detect_python_version(self, service_path: Path) -> str:
        """Detect Python version from .python-version file.

        Args:
            service_path: Path to service directory

        Returns:
            Python version string (e.g., "3.12")
        """
        python_version_file = service_path / ".python-version"
        if python_version_file.exists():
            try:
                version = python_version_file.read_text().strip()
                # Extract major.minor (e.g., "3.12.0" → "3.12")
                parts = version.split(".")
                if len(parts) >= 2:
                    return f"{parts[0]}.{parts[1]}"
            except (IOError, ValueError):
                pass

        # Default to 3.12
        return "3.12"

    def _detect_dependency_manager(self, service_path: Path) -> dict[str, bool]:
        """Detect Python dependency manager from marker files.

        Delegates to the scanner's detect_python_dep_manager - the single
        source of truth for dependency-manager priority (uv → Poetry →
        PEP 621 → Pipenv → pip). uv projects install via the pep621 template
        path - the flyctl Dockerfile template has no uv-specific branch.

        Args:
            service_path: Path to service directory

        Returns:
            Dictionary with boolean flags for each manager
        """
        from slipp.scanner.helpers import detect_python_dep_manager

        managers = {
            "poetry": False,
            "pipenv": False,
            "pep621": False,
            "pip": False,
        }

        detected = detect_python_dep_manager(service_path)
        if detected == "uv":
            managers["pep621"] = True
        elif detected is not None:
            managers[detected] = True

        return managers

    def _find_streamlit_entrypoint(self, service_path: Path) -> str:
        """Find Streamlit entrypoint file.

        Args:
            service_path: Path to service directory

        Returns:
            Entrypoint filename (default: "app.py")
        """
        # Common Streamlit entrypoint names
        candidates = ["app.py", "main.py", "streamlit_app.py"]

        for candidate in candidates:
            if (service_path / candidate).exists():
                return candidate

        # Default fallback
        return "app.py"
