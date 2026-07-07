"""Shared Node.js project introspection helpers."""

from pathlib import Path


def detect_package_manager(path: Path) -> tuple[str, str]:
    """Detect package manager from lock files.

    Args:
        path: Path to a directory containing package.json

    Returns:
        Tuple of (package_manager, package_files)
        e.g., ("yarn", "package.json yarn.lock")
    """
    if (path / "yarn.lock").exists():
        return ("yarn", "package.json yarn.lock")
    elif (path / "pnpm-lock.yaml").exists():
        return ("pnpm", "package.json pnpm-lock.yaml")
    elif (path / "bun.lockb").exists():
        return ("bun", "package.json bun.lockb")
    elif (path / "package-lock.json").exists():
        return ("npm", "package.json package-lock.json")
    else:
        # No lock file found, default to npm
        return ("npm", "package.json package-lock.json")
