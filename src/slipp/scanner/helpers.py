"""Scanner helper utilities.

Provides utility functions for framework detection that mirror flyctl's
helpers.go patterns. All checks are composable and return bool.
"""

import functools
import json
import logging
import re
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

PythonDepManager = Literal["uv", "poetry", "pep621", "pipenv", "pip"]

# Fly.io template URLs (matches flyctl). Shared by every detector that emits
# the given family, so the two families can't drift apart on template updates.
PYTHON_DOCKER_TEMPLATE = "https://raw.githubusercontent.com/superfly/flyctl/master/scanner/templates/python-docker/Dockerfile"
NODE_DOCKER_TEMPLATE = "https://raw.githubusercontent.com/superfly/flyctl/master/scanner/templates/node/Dockerfile"

# Default ports, shared the same way so the two families can't drift apart.
DEFAULT_PYTHON_PORT = 8080
DEFAULT_NODE_PORT = 3000


@functools.lru_cache
def load_pyproject(source_dir: Path) -> dict | None:
    """Parse pyproject.toml once per source_dir, memoized across detectors.

    Returns:
        Parsed TOML data, or None if the file doesn't exist or can't be parsed
    """
    pyproject = source_dir / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        import tomllib

        with open(pyproject, "rb") as f:
            return tomllib.load(f)
    except Exception:
        logger.debug("Failed to parse %s", pyproject, exc_info=True)
        return None


def has_uv_project(source_dir: Path) -> bool:
    """Check if directory is a uv project.

    Detection signals (priority order):
    1. uv.lock exists (strongest signal)
    2. pyproject.toml with [tool.uv] section
    3. pyproject.toml with uv_build backend
    4. pyproject.toml with [dependency-groups] + .python-version

    Args:
        source_dir: Directory to check

    Returns:
        True if uv project detected, False otherwise
    """
    if (source_dir / "uv.lock").exists():
        return True

    data = load_pyproject(source_dir)
    if data is not None:
        if "uv" in data.get("tool", {}):
            return True

        build_backend = data.get("build-system", {}).get("build-backend", "")
        if build_backend == "uv_build":
            return True

        if "dependency-groups" in data and (source_dir / ".python-version").exists():
            return True

    return False


def detect_python_dep_manager(source_dir: Path) -> PythonDepManager | None:
    """Detect a Python project's dependency manager, priority-ordered.

    Single source of truth for both the scanner (framework detection) and the
    Dockerfile extractor (template variable selection) - they previously
    diverged on Pipfile vs PEP 621 ordering, which could pick the wrong
    Dockerfile branch for a project containing both files.

    Priority: uv -> Poetry -> PEP 621 pyproject.toml -> Pipenv -> requirements.txt

    Args:
        source_dir: Directory to check

    Returns:
        The detected manager, or None if no recognized marker file is found
    """
    if has_uv_project(source_dir):
        return "uv"

    if (source_dir / "poetry.lock").exists() and (
        source_dir / "pyproject.toml"
    ).exists():
        return "poetry"

    data = load_pyproject(source_dir)
    if data is not None and "project" in data:
        return "pep621"

    if (source_dir / "Pipfile").exists():
        return "pipenv"

    if (source_dir / "requirements.txt").exists():
        return "pip"

    return None


def file_exists(source_dir: Path, *filenames: str) -> bool:
    """Check whether any of the given filenames exists in source_dir.

    Mirrors flyctl's fileExists (helpers.go line 36).

    Args:
        source_dir: Directory to check
        *filenames: One or more filenames to check

    Returns:
        True if any of the named files exists

    Example:
        >>> file_exists(Path("/path/to/project"), "setup.py", "pyproject.toml")
    """
    return any((source_dir / filename).exists() for filename in filenames)


def parse_dependency(dep: str) -> str:
    """Parse dependency string to extract package name.

    Handles various version specifiers and markers:
    - Environment markers: "django>=3.0; python_version >= '3.8'"
    - Extras: "requests[security]>=2.0"
    - Version constraints: "pytest==7.0.0", "numpy>=1.20", "pandas~=1.3"

    Args:
        dep: Dependency string from requirements file or pyproject.toml

    Returns:
        Normalized package name (lowercase, no version specifiers)

    Example:
        >>> parse_dependency("Flask>=2.0.0; python_version >= '3.8'")
        'flask'
    """
    dep = dep.split(";")[0]
    dep = dep.split("[")[0]
    dep = re.split(r"[<>=!~]", dep, maxsplit=1)[0]
    return dep.strip().lower()


def parse_pyproject_dependencies(source_dir: Path) -> list[str]:
    """Parse dependencies from pyproject.toml (PEP 621 and Poetry formats).

    Extracts and normalizes package names from:
    - [project].dependencies (PEP 621 standard)
    - [tool.poetry].dependencies (Poetry format)

    Args:
        source_dir: Directory containing pyproject.toml

    Returns:
        List of normalized package names (lowercase, no version specifiers)
        Empty list if pyproject.toml doesn't exist or can't be parsed

    Example:
        >>> deps = parse_pyproject_dependencies(Path("/path/to/project"))
        >>> "flask" in deps
        True
    """
    data = load_pyproject(source_dir)
    if data is None:
        return []

    dependencies = []

    pep621_deps = data.get("project", {}).get("dependencies", [])
    for dep in pep621_deps:
        dependencies.append(parse_dependency(dep))

    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    for package_name in poetry_deps.keys():
        if package_name.lower() != "python":
            dependencies.append(package_name.lower())

    return dependencies


def parse_pipfile_dependencies(source_dir: Path) -> list[str]:
    """Parse dependencies from Pipfile's [packages] table.

    Args:
        source_dir: Directory containing Pipfile

    Returns:
        List of normalized package names (lowercase)
        Empty list if Pipfile doesn't exist or can't be parsed
    """
    pipfile = source_dir / "Pipfile"
    if not pipfile.exists():
        return []

    try:
        import tomllib

        with open(pipfile, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        logger.debug("Failed to parse %s", pipfile, exc_info=True)
        return []

    return [name.lower() for name in data.get("packages", {}).keys()]


def parse_setup_cfg_dependencies(source_dir: Path) -> list[str]:
    """Parse dependencies from setup.cfg's [options] install_requires.

    Args:
        source_dir: Directory containing setup.cfg

    Returns:
        List of normalized package names (lowercase)
        Empty list if setup.cfg doesn't exist, has no install_requires, or
        can't be parsed
    """
    setup_cfg = source_dir / "setup.cfg"
    if not setup_cfg.exists():
        return []

    import configparser

    parser = configparser.ConfigParser()
    try:
        parser.read(setup_cfg)
    except configparser.Error:
        logger.debug("Failed to parse %s", setup_cfg, exc_info=True)
        return []

    install_requires = parser.get("options", "install_requires", fallback="")
    dependencies = []
    for line in install_requires.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            package = parse_dependency(line)
            if package:
                dependencies.append(package)

    return dependencies


def extract_python_dependencies(source_dir: Path) -> list[str]:
    """Extract all Python dependencies from multiple formats (centralized).

    Checks Python dependency formats in priority order:
    1. pyproject.toml (PEP 621 and Poetry formats)
    2. requirements.txt
    3. Pipfile ([packages] table)
    4. setup.cfg ([options] install_requires)

    setup.py is intentionally not parsed: its dependency list is defined by
    executing arbitrary Python (the `install_requires=` kwarg to `setup()`),
    which can't be statically extracted without running it.

    This function provides centralized extraction that framework detectors
    can call when needed, eliminating duplicate parsing logic.

    Args:
        source_dir: Directory to scan for Python dependency files

    Returns:
        Sorted list of normalized package names (lowercase, deduplicated)
        Empty list if no dependency files found

    Example:
        >>> deps = extract_python_dependencies(Path("/path/to/flask-app"))
        >>> "flask" in deps
        True
        >>> "uvicorn" in deps
        True
    """
    dependencies = set()

    dependencies.update(parse_pyproject_dependencies(source_dir))

    requirements_file = source_dir / "requirements.txt"
    if requirements_file.exists():
        try:
            content = requirements_file.read_text()
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    package = parse_dependency(line)
                    if package:
                        dependencies.add(package)
        except (IOError, UnicodeDecodeError):
            pass

    dependencies.update(parse_pipfile_dependencies(source_dir))
    dependencies.update(parse_setup_cfg_dependencies(source_dir))

    return sorted(dependencies)


def extract_nodejs_dependencies(source_dir: Path) -> list[str]:
    """Extract all Node.js dependencies from package.json (centralized).

    Extracts from both dependencies and devDependencies sections.
    Preserves @ prefix for scoped packages (e.g., @sveltejs/kit).

    This function provides centralized extraction that framework detectors
    can call when needed, eliminating duplicate parsing logic.

    Args:
        source_dir: Directory containing package.json

    Returns:
        Sorted list of package names (preserves @ prefix, deduplicated)
        Empty list if package.json doesn't exist or can't be parsed

    Example:
        >>> deps = extract_nodejs_dependencies(Path("/path/to/sveltekit-app"))
        >>> "@sveltejs/kit" in deps
        True
        >>> "vite" in deps
        True
    """
    package_json = source_dir / "package.json"
    if not package_json.exists():
        return []

    try:
        with open(package_json) as f:
            config_data = json.load(f)

        dependencies = set()
        dependencies.update(config_data.get("dependencies", {}).keys())
        dependencies.update(config_data.get("devDependencies", {}).keys())
        return sorted(dependencies)

    except (json.JSONDecodeError, IOError):
        return []
