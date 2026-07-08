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
        """Extract Node.js template variables from DetectedService."""
        variables: dict[str, Any] = {}

        variables["appName"] = service.name
        variables["port"] = service.port

        pkg = self._load_package_json(service.path)

        variables["nodeVersion"] = self._detect_nodejs_version(service.path, pkg)

        package_manager, package_files = detect_package_manager(service.path)
        variables["packager"] = package_manager
        variables["package_files"] = package_files

        if package_manager == "yarn":
            variables["yarn"] = True
            variables["yarnVersion"] = "1.22.0"
        else:
            variables["yarn"] = False

        variables["runtime"] = self._get_runtime_name(service.framework)

        variables["prisma"] = "@prisma/client" in service.dependencies
        variables["build"] = "build" in pkg.get("scripts", {}) if pkg else False
        variables["devDependencies"] = (
            bool(pkg.get("devDependencies")) if pkg else False
        )

        return variables

    @staticmethod
    def _load_package_json(service_path: Path) -> dict[str, Any] | None:
        """Load and parse package.json, returning None on missing/invalid."""
        package_json = service_path / "package.json"
        if not package_json.exists():
            return None
        try:
            return json.loads(package_json.read_text())
        except (json.JSONDecodeError, IOError):
            return None

    def _detect_nodejs_version(
        self, service_path: Path, pkg: dict[str, Any] | None
    ) -> str:
        """Detect Node.js version from .nvmrc or package.json engines."""
        nvmrc = service_path / ".nvmrc"
        if nvmrc.exists():
            try:
                version = nvmrc.read_text().strip().lstrip("v")
                parts = version.split(".")
                if parts:
                    return parts[0]
            except (IOError, ValueError):
                pass

        if pkg:
            node_version = pkg.get("engines", {}).get("node", "")
            if node_version:
                match = re.search(r"\d+", node_version)
                if match:
                    return match.group(0)

        return "20"

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
