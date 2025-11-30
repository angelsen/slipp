"""Generic Python framework detector.

Detects Python projects with priority-based detection for modern tooling.
Enhanced version: uv → Poetry → PEP 621 → Pipenv → pip (supersedes flyctl).

Mirrors and extends flyctl's python.go patterns.
"""

from pathlib import Path
from typing import Optional

from slipp.scanner.helpers import (
    checks_pass,
    extract_python_dependencies,
    file_exists,
)
from slipp.scanner.models import ScannerConfig, SourceInfo

# Fly.io template URL (matches flyctl)
PYTHON_TEMPLATE = "https://raw.githubusercontent.com/superfly/flyctl/master/scanner/templates/python-docker/Dockerfile"


def _has_uv_project(source_dir: Path) -> bool:
    """Check if directory is a uv project (internal helper).

    Detection signals (priority order):
    1. uv.lock exists (strongest signal - 95% confidence)
    2. pyproject.toml with [tool.uv] section (90% confidence)
    3. pyproject.toml with uv_build backend (100% confidence)
    4. pyproject.toml with [dependency-groups] + .python-version (60% confidence)

    Returns:
        True if uv project detected, False otherwise
    """
    # Priority 1: uv.lock (definitive)
    if (source_dir / "uv.lock").exists():
        return True

    # Priority 2-4: pyproject.toml analysis
    pyproject = source_dir / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib

            with open(pyproject, "rb") as f:
                data = tomllib.load(f)

            # Priority 2: [tool.uv] section
            if "uv" in data.get("tool", {}):
                return True

            # Priority 3: uv_build backend
            build_backend = data.get("build-system", {}).get("build-backend", "")
            if build_backend == "uv_build":
                return True

            # Priority 4: PEP 735 dependency-groups + .python-version (weak)
            if (
                "dependency-groups" in data
                and (source_dir / ".python-version").exists()
            ):
                return True

        except (ImportError, IOError, Exception):
            pass

    return False


def _has_poetry_project(source_dir: Path) -> bool:
    """Check if directory is a Poetry project (internal helper).

    Matches flyctl's Poetry detection: requires BOTH files.

    Returns:
        True if Poetry project detected, False otherwise
    """
    return (source_dir / "poetry.lock").exists() and (
        source_dir / "pyproject.toml"
    ).exists()


def configure_python(
    source_dir: Path,
    config: ScannerConfig,
) -> Optional[SourceInfo]:
    """Configure generic Python application.

    Enhanced priority-based detection (supersedes flyctl with uv support):
    1. uv (NEW - modern package manager, ahead of flyctl)
    2. Poetry (matches flyctl)
    3. PEP 621 pyproject.toml (matches flyctl)
    4. Pipenv (matches flyctl)
    5. pip/requirements.txt (matches flyctl)
    6. Generic fallback (setup.py, setup.cfg, environment.yml)

    Extracts dependencies internally using language-specific helper.

    Args:
        source_dir: Directory to scan
        config: Scanner configuration (unused in MVP)

    Returns:
        SourceInfo if Python project detected, None otherwise

    Example:
        >>> info = configure_python(Path("/path/to/python-app"), ScannerConfig())
        >>> info.family
        'Python'
        >>> info.port
        8080
    """
    # Priority 1: uv (NEW - supersede flyctl)
    if _has_uv_project(source_dir):
        dependencies = extract_python_dependencies(source_dir)
        return SourceInfo(
            family="Python",
            port=8080,
            template_url=PYTHON_TEMPLATE,
            env_vars={"PORT": "8080"},
            dependencies=dependencies,
            # TODO: Use uv-optimized template in future
        )

    # Priority 2: Poetry (match flyctl)
    if _has_poetry_project(source_dir):
        dependencies = extract_python_dependencies(source_dir)
        return SourceInfo(
            family="Python",
            port=8080,
            template_url=PYTHON_TEMPLATE,
            env_vars={"PORT": "8080"},
            dependencies=dependencies,
            # TODO: Use poetry-optimized template in future
        )

    # Priority 3: PEP 621 pyproject.toml (match flyctl)
    # Check for pyproject.toml with [project] section (not Poetry, not uv)
    pyproject = source_dir / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib

            with open(pyproject, "rb") as f:
                data = tomllib.load(f)

            # Has [project] section = PEP 621
            if "project" in data:
                dependencies = extract_python_dependencies(source_dir)
                return SourceInfo(
                    family="Python",
                    port=8080,
                    template_url=PYTHON_TEMPLATE,
                    env_vars={"PORT": "8080"},
                    dependencies=dependencies,
                )
        except (ImportError, IOError, Exception):
            pass

    # Priority 4: Pipenv (match flyctl)
    if (source_dir / "Pipfile").exists():
        dependencies = extract_python_dependencies(source_dir)
        return SourceInfo(
            family="Python",
            port=8080,
            template_url=PYTHON_TEMPLATE,
            env_vars={"PORT": "8080"},
            dependencies=dependencies,
        )

    # Priority 5: pip/requirements.txt (match flyctl)
    if (source_dir / "requirements.txt").exists():
        dependencies = extract_python_dependencies(source_dir)
        return SourceInfo(
            family="Python",
            port=8080,
            template_url=PYTHON_TEMPLATE,
            env_vars={"PORT": "8080"},
            dependencies=dependencies,
        )

    # Fallback: Generic Python (match flyctl)
    if checks_pass(
        source_dir,
        file_exists("setup.py", "setup.cfg", "environment.yml"),
    ):
        dependencies = extract_python_dependencies(source_dir)
        return SourceInfo(
            family="Python",
            port=8080,
            template_url=PYTHON_TEMPLATE,
            env_vars={"PORT": "8080"},
            dependencies=dependencies,
        )

    return None
