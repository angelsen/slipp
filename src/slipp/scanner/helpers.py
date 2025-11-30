"""Scanner helper utilities.

Provides utility functions for framework detection that mirror flyctl's
helpers.go patterns. All checks are composable and return bool.
"""

import json
import re
from pathlib import Path
from typing import Callable

# Type alias for check functions (matches flyctl's checkFn)
CheckFn = Callable[[Path], bool]


def checks_pass(source_dir: Path, *checks: CheckFn) -> bool:
    """Run multiple checks, return True if ANY pass (OR logic).

    Mirrors flyctl's checksPass function (helpers.go line 28).

    Args:
        source_dir: Directory to check
        *checks: Variable number of check functions

    Returns:
        True if any check passes, False if all fail

    Example:
        >>> checks_pass(
        ...     path,
        ...     file_exists("setup.py"),
        ...     file_exists("pyproject.toml")
        ... )
    """
    for check in checks:
        if check(source_dir):
            return True
    return False


def file_exists(*filenames: str) -> CheckFn:
    """Create check function for file existence.

    Mirrors flyctl's fileExists (helpers.go line 36).

    Args:
        *filenames: One or more filenames to check

    Returns:
        Check function that returns True if any file exists

    Example:
        >>> check = file_exists("setup.py", "pyproject.toml")
        >>> check(Path("/path/to/project"))  # True if either exists
    """

    def check(source_dir: Path) -> bool:
        return any((source_dir / filename).exists() for filename in filenames)

    return check


def dir_contains(filename: str, pattern: str) -> CheckFn:
    """Create check function for pattern in file.

    Mirrors flyctl's dirContains (helpers.go line 48).
    Uses regex with case-insensitive flag by default.

    Args:
        filename: File to check (e.g., "requirements.txt")
        pattern: Regex pattern to search for (e.g., "(?i)Flask")

    Returns:
        Check function that returns True if pattern found in file

    Example:
        >>> check = dir_contains("requirements.txt", "(?i)Flask")
        >>> check(Path("/path/to/project"))  # True if Flask in requirements.txt
    """

    def check(source_dir: Path) -> bool:
        file_path = source_dir / filename
        if not file_path.exists():
            return False

        try:
            content = file_path.read_text()
            # Pattern can include (?i) for case-insensitive
            return re.search(pattern, content) is not None
        except (IOError, UnicodeDecodeError):
            return False

    return check


def is_in_virtual_env(file_path: Path) -> bool:
    """Check if path is inside a virtual environment.

    Filters out false positives from site-packages, .venv, etc.
    Ported from .bak/detector.py.

    Args:
        file_path: Path to check

    Returns:
        True if path is in a virtual environment

    Example:
        >>> is_in_virtual_env(Path("/project/.venv/lib/python3.12/site-packages/django/wsgi.py"))
        True
    """
    path_str = str(file_path)
    return any(
        venv_marker in path_str
        for venv_marker in [
            "site-packages",
            ".venv",
            "venv",
            ".virtualenv",
            "env",
            ".tox",
        ]
    )


def parse_dependency(dep: str) -> str:
    """Parse dependency string to extract package name.

    Handles various version specifiers and markers:
    - Environment markers: "django>=3.0; python_version >= '3.8'"
    - Extras: "requests[security]>=2.0"
    - Version constraints: "pytest==7.0.0", "numpy>=1.20", "pandas~=1.3"

    Ported from .bak/detector.py.

    Args:
        dep: Dependency string from requirements file or pyproject.toml

    Returns:
        Normalized package name (lowercase, no version specifiers)

    Example:
        >>> parse_dependency("Flask>=2.0.0; python_version >= '3.8'")
        'flask'
    """
    # Remove environment markers (after semicolon)
    dep = dep.split(";")[0]
    # Remove extras (in square brackets)
    dep = dep.split("[")[0]
    # Remove version specifiers
    dep = dep.split(">=")[0].split("==")[0].split("~=")[0].split("<")[0].split(">")[0]
    # Remove whitespace and lowercase
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
    pyproject = source_dir / "pyproject.toml"
    if not pyproject.exists():
        return []

    try:
        import tomllib

        with open(pyproject, "rb") as f:
            data = tomllib.load(f)

        dependencies = []

        # Extract PEP 621 dependencies
        pep621_deps = data.get("project", {}).get("dependencies", [])
        for dep in pep621_deps:
            dependencies.append(parse_dependency(dep))

        # Extract Poetry dependencies
        poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        for package_name in poetry_deps.keys():
            # Skip 'python' key (it's a version specifier, not a package)
            if package_name.lower() != "python":
                dependencies.append(package_name.lower())

        return dependencies

    except (ImportError, IOError):
        # tomllib not available (Python < 3.11) or file not readable
        return []
    except Exception:
        # TOML parsing error or other unexpected issue
        return []


def extract_python_dependencies(source_dir: Path) -> list[str]:
    """Extract all Python dependencies from multiple formats (centralized).

    Checks Python dependency formats in priority order:
    1. pyproject.toml (PEP 621 and Poetry formats)
    2. requirements.txt

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
    dependencies = set()  # Use set for automatic deduplication

    # Priority 1: pyproject.toml (handles both PEP 621 and Poetry)
    pyproject_deps = parse_pyproject_dependencies(source_dir)
    dependencies.update(pyproject_deps)

    # Priority 2: requirements.txt
    requirements_file = source_dir / "requirements.txt"
    if requirements_file.exists():
        try:
            content = requirements_file.read_text()
            for line in content.splitlines():
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith("#"):
                    package = parse_dependency(line)
                    if package:  # Only add non-empty packages
                        dependencies.add(package)
        except (IOError, UnicodeDecodeError):
            # File not readable, skip
            pass

    # Convert set to sorted list for consistent ordering
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

        dependencies = set()  # Use set for automatic deduplication

        # Extract dependencies
        deps = config_data.get("dependencies", {})
        dependencies.update(deps.keys())

        # Extract devDependencies
        dev_deps = config_data.get("devDependencies", {})
        dependencies.update(dev_deps.keys())

        # Convert set to sorted list for consistent ordering
        return sorted(dependencies)

    except (json.JSONDecodeError, IOError):
        # File not readable or invalid JSON, return empty list
        return []
