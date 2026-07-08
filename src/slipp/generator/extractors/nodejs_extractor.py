"""Node.js variable extractor for template rendering.

Extracts template variables for all Node.js frameworks (SvelteKit, Next.js, Nuxt, etc.).
"""

import json
import re
from pathlib import Path
from typing import Any

from slipp.generator.extractors.base import VariableExtractor
from slipp.models.deployment import DetectedService
from slipp.utils.nodejs import detect_package_manager


class NodeJSVariableExtractor(VariableExtractor):
    """Extract template variables for Node.js frameworks.

    Handles all Node.js-based frameworks: SvelteKit, Next.js, Nuxt, Express, etc.
    Reusable across different Node.js frameworks since they share the same template variables.
    """

    def extract(self, service: DetectedService) -> dict[str, Any]:
        """Extract Node.js template variables from DetectedService.

        Args:
            service: Detected Node.js service

        Returns:
            Dictionary of Node.js template variables

        Example:
            >>> service = DetectedService(
            ...     name="frontend",
            ...     framework="sveltekit",
            ...     path=Path("examples/PoC/packages/frontend"),
            ...     dependencies=["@sveltejs/kit", "vite"],
            ...     port=3000
            ... )
            >>> extractor = NodeJSVariableExtractor()
            >>> vars = extractor.extract(service)
            >>> vars["nodeVersion"]
            '20'
            >>> vars["packager"]
            'npm'
        """
        variables = {}

        # Common variables
        variables["appName"] = service.name
        variables["port"] = service.port

        # Node version detection
        variables["nodeVersion"] = self._detect_nodejs_version(service.path)

        # Package manager detection
        package_manager, package_files = detect_package_manager(service.path)
        variables["packager"] = package_manager
        variables["package_files"] = package_files

        # Yarn-specific variables
        if package_manager == "yarn":
            variables["yarn"] = True
            variables["yarnVersion"] = "1.22.0"  # Default Yarn 1.x version
        else:
            variables["yarn"] = False

        # Runtime/framework name (for Docker labels)
        variables["runtime"] = self._get_runtime_name(service.framework)

        # Feature detection
        variables["prisma"] = "@prisma/client" in service.dependencies
        variables["build"] = self._has_build_script(service.path)
        variables["devDependencies"] = self._has_dev_dependencies(service.path)

        return variables

    def _detect_nodejs_version(self, service_path: Path) -> str:
        """Detect Node.js version from .nvmrc or package.json.

        Args:
            service_path: Path to service directory

        Returns:
            Node.js major version string (e.g., "20")
        """
        # Check .nvmrc
        nvmrc = service_path / ".nvmrc"
        if nvmrc.exists():
            try:
                version = nvmrc.read_text().strip()
                # Extract major version (e.g., "v20.0.0" → "20", "20" → "20")
                version = version.lstrip("v")
                parts = version.split(".")
                if parts:
                    return parts[0]
            except (IOError, ValueError):
                pass

        # Check package.json engines.node field
        package_json = service_path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text())
                engines = data.get("engines", {})
                node_version = engines.get("node", "")

                if node_version:
                    # Parse version specifier (e.g., ">=20.0.0", "^20", "20.x")
                    # Extract first number
                    match = re.search(r"\d+", node_version)
                    if match:
                        return match.group(0)
            except (json.JSONDecodeError, IOError):
                pass

        # Default to LTS version
        return "20"

    def _has_build_script(self, service_path: Path) -> bool:
        """Check if package.json has a build script.

        Args:
            service_path: Path to service directory

        Returns:
            True if build script exists
        """
        package_json = service_path / "package.json"
        if not package_json.exists():
            return False

        try:
            data = json.loads(package_json.read_text())
            scripts = data.get("scripts", {})
            return "build" in scripts
        except (json.JSONDecodeError, IOError):
            return False

    def _has_dev_dependencies(self, service_path: Path) -> bool:
        """Check if package.json declares any devDependencies.

        Reads package.json directly rather than service.dependencies, which
        merges dependencies and devDependencies together (see
        scanner/helpers.py:extract_nodejs_dependencies) and would be true
        for nearly any Node project regardless of whether it has dev-only
        packages.

        Args:
            service_path: Path to service directory

        Returns:
            True if package.json has a non-empty devDependencies section
        """
        package_json = service_path / "package.json"
        if not package_json.exists():
            return False

        try:
            data = json.loads(package_json.read_text())
            return bool(data.get("devDependencies"))
        except (json.JSONDecodeError, IOError):
            return False

    def _get_runtime_name(self, framework: str) -> str:
        """Get human-readable runtime name for Docker label.

        Args:
            framework: Framework name from scanner

        Returns:
            Runtime name string
        """
        # Keys match slipp.scanner.models.NODE_FRAMEWORKS (sveltekit, node) -
        # nextjs/nuxtjs/express/remix have no scanner detector.
        runtime_map = {
            "sveltekit": "SvelteKit",
            "node": "Node.js",
        }

        return runtime_map.get(framework, "Node.js")
