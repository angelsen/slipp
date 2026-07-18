"""Shared Node.js project introspection helpers."""

from pathlib import Path


def detect_package_manager(path: Path) -> tuple[str, str]:
    """Detect package manager from lock files.

    Args:
        path: Path to a directory containing package.json

    Returns:
        Tuple of (package_manager, package_files)
        e.g., ("yarn", "package.json yarn.lock")

    package_files only ever names files that actually exist -- matching
    flyctl's own node.go, which appends a lockfile to the COPY list solely
    when os.Stat confirms it's there. Defaulting to "package.json
    package-lock.json" here even without a real lock file (fixed
    2026-07-18) both COPYed a nonexistent file and, since it's flyctl's
    only lockfile-less case, the sole way the Node Dockerfile template's
    `COPY --link {{ .package_files }} .` line ever rendered as
    single-source -- multi-source with the template's bare "." dest is a
    separate, still-live Docker/Podman COPY syntax error (see
    generator.py's _fix_copy_dest()).
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
        return ("npm", "package.json")
