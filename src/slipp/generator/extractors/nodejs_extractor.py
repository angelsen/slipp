"""Node.js variable extractor for template rendering.

Extracts template variables for Node.js services. The scanner only detects
SvelteKit and generic Node today; the extraction logic itself is generic
enough to cover other frameworks once a scanner detector exists for them.
"""

import re
from pathlib import Path
from typing import Any

from slipp.models.deployment import DetectedService
from slipp.scanner.models import NODE_FRAMEWORKS
from slipp.utils.files import read_json_file
from slipp.utils.nodejs import detect_package_manager

# Human-readable runtime name and systemd ExecStart entrypoint per Node
# framework. Keys must match NODE_FRAMEWORKS exactly (asserted below) so
# adding a framework there without updating this map fails loudly at import
# time instead of with a bare KeyError deep in extraction.
_RUNTIME_NAMES = {
    "sveltekit": "SvelteKit",
    "node": "Node.js",
}
_EXEC_STARTS = {
    "sveltekit": "node build",
    "node": "node .",
}
if (
    _RUNTIME_NAMES.keys() != _EXEC_STARTS.keys()
    or _RUNTIME_NAMES.keys() != NODE_FRAMEWORKS
):
    raise RuntimeError(
        "_RUNTIME_NAMES, _EXEC_STARTS, and NODE_FRAMEWORKS have drifted apart"
    )


def extract_nodejs(service: DetectedService) -> dict[str, Any]:
    """Extract Node.js template variables from DetectedService.

    Reusable across Node.js frameworks since they share the same template
    variables; currently exercised by SvelteKit and generic Node (the only
    frameworks the scanner detects).
    """
    variables: dict[str, Any] = {}

    pkg = _load_package_json(service.path)

    variables["nodeVersion"] = _detect_nodejs_version(service.path, pkg)

    package_manager, package_files = detect_package_manager(service.path)
    variables["packager"] = package_manager
    variables["package_files"] = package_files
    variables["install_command"] = _install_command(package_manager)
    variables["build_command"] = f"{package_manager} run build"

    if package_manager == "yarn":
        variables["yarn"] = True
        variables["yarnVersion"] = _detect_yarn_version(pkg)
    else:
        variables["yarn"] = False

    variables["runtime"] = _get_runtime_name(service.framework)

    variables["prisma"] = "@prisma/client" in service.dependencies
    variables["build"] = "build" in pkg.get("scripts", {}) if pkg else False
    variables["devDependencies"] = bool(pkg.get("devDependencies")) if pkg else False
    variables["exec_start"] = _get_exec_start(service.framework)

    return variables


def _install_command(package_manager: str) -> str:
    """Reproducible-install command for the detected package manager."""
    commands = {
        "yarn": "yarn install --frozen-lockfile",
        "pnpm": "pnpm install --frozen-lockfile",
        "bun": "bun install --frozen-lockfile",
    }
    return commands.get(package_manager, "npm ci")


def _detect_yarn_version(pkg: dict[str, Any] | None) -> str:
    """Detect Yarn version from package.json's packageManager field.

    Modern Yarn (Berry/2+) declares itself via "packageManager": "yarn@x.y.z"
    (Corepack convention); classic Yarn projects don't set this, so falling
    back to 1.22.0 there is correct.
    """
    if pkg:
        package_manager = pkg.get("packageManager", "")
        match = re.match(r"yarn@(\d+\.\d+\.\d+)", package_manager)
        if match:
            return match.group(1)

    return "1.22.0"


def _load_package_json(service_path: Path) -> dict[str, Any] | None:
    """Load and parse package.json, returning None on missing/invalid."""
    return read_json_file(service_path / "package.json")


def _detect_nodejs_version(service_path: Path, pkg: dict[str, Any] | None) -> str:
    """Detect Node.js version from .nvmrc or package.json engines."""
    nvmrc = service_path / ".nvmrc"
    if nvmrc.exists():
        try:
            version = nvmrc.read_text().strip().lstrip("v")
            major = version.split(".")[0]
            if major.isdigit():
                return major
        except (OSError, UnicodeDecodeError, ValueError):
            pass

    if pkg:
        node_version = pkg.get("engines", {}).get("node", "")
        if node_version:
            match = re.search(r"\d+", node_version)
            if match:
                return match.group(0)

    return "20"


def _get_runtime_name(framework: str) -> str:
    """Get human-readable runtime name for Docker label.

    Args:
        framework: Framework name from scanner. Always one of
            slipp.scanner.models.NODE_FRAMEWORKS (sveltekit, node) - this is
            only reachable via the EXTRACTORS registry, which wires
            extract_nodejs to exactly those two names.

    Returns:
        Runtime name string
    """
    return _RUNTIME_NAMES[framework]


def _get_exec_start(framework: str) -> str:
    """Get the systemd ExecStart entrypoint (relative to /usr/bin/) for a framework.

    SvelteKit's adapter-node always emits a `build/` entrypoint. Generic
    Node has no such convention -- `node .` runs package.json's `main`
    (or index.js), which is what plain `node` invocation does by default.

    Args:
        framework: Framework name from scanner, see _get_runtime_name.

    Returns:
        Entrypoint command, without the /usr/bin/ prefix (e.g. "node build")
    """
    return _EXEC_STARTS[framework]
