"""Generic Python framework detector.

Detects Python projects with priority-based detection for modern tooling.
Enhanced version: uv → Poetry → PEP 621 → Pipenv → pip (supersedes flyctl).

Mirrors and extends flyctl's python.go patterns.
"""

from pathlib import Path

from slipp.scanner.helpers import (
    checks_pass,
    extract_python_dependencies,
    file_exists,
)
from slipp.scanner.models import ScannerConfig, SourceInfo

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
    if (source_dir / "uv.lock").exists():
        return True

    pyproject = source_dir / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib

            with open(pyproject, "rb") as f:
                data = tomllib.load(f)

            if "uv" in data.get("tool", {}):
                return True

            build_backend = data.get("build-system", {}).get("build-backend", "")
            if build_backend == "uv_build":
                return True

            if (
                "dependency-groups" in data
                and (source_dir / ".python-version").exists()
            ):
                return True

        except (ImportError, IOError, Exception):
            pass

    return False


def _has_poetry_project(source_dir: Path) -> bool:
    """Check if directory is a Poetry project (requires poetry.lock and pyproject.toml)."""
    return (source_dir / "poetry.lock").exists() and (
        source_dir / "pyproject.toml"
    ).exists()


def configure_python(
    source_dir: Path,
    config: ScannerConfig,
) -> SourceInfo | None:
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

    pyproject = source_dir / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib

            with open(pyproject, "rb") as f:
                data = tomllib.load(f)

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

    if (source_dir / "Pipfile").exists():
        dependencies = extract_python_dependencies(source_dir)
        return SourceInfo(
            family="Python",
            port=8080,
            template_url=PYTHON_TEMPLATE,
            env_vars={"PORT": "8080"},
            dependencies=dependencies,
        )

    if (source_dir / "requirements.txt").exists():
        dependencies = extract_python_dependencies(source_dir)
        return SourceInfo(
            family="Python",
            port=8080,
            template_url=PYTHON_TEMPLATE,
            env_vars={"PORT": "8080"},
            dependencies=dependencies,
        )

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
