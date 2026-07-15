"""npm/yarn workspace member detection for slipp launch.

Lets `slipp launch` (run with no --dir flags) auto-discover every app in a
package.json "workspaces" monorepo instead of requiring the user to type
out every subdirectory by hand.
"""

import json
import shutil
import subprocess
from pathlib import Path

from slipp.utils.nodejs import detect_package_manager


def _resolve_via_npm(root: Path) -> list[Path] | None:
    """Resolve workspace members via `npm query .workspace --json`.

    Returns None (not []) on any failure so the caller can fall back to
    glob resolution -- an empty result here would be indistinguishable
    from "genuinely no members".
    """
    if not shutil.which("npm"):
        return None
    try:
        result = subprocess.run(
            ["npm", "query", ".workspace", "--json"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        entries = json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None

    return [root / entry["location"] for entry in entries if "location" in entry]


def _resolve_via_yarn(root: Path) -> list[Path] | None:
    """Resolve workspace members via `yarn workspaces list --json` (Yarn Berry).

    Output is newline-delimited JSON objects, not a single JSON array.
    """
    if not shutil.which("yarn"):
        return None
    try:
        result = subprocess.run(
            ["yarn", "workspaces", "list", "--json"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return None

    members = []
    try:
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if "location" in entry:
                members.append(root / entry["location"])
    except json.JSONDecodeError:
        return None

    return members


def _resolve_via_glob(root: Path, patterns: list[str]) -> list[Path]:
    """Naive fallback: glob each workspace pattern, keep real packages.

    Used only when the native package-manager command isn't available.
    Doesn't support negation patterns (e.g. "!packages/excluded") -- only
    the native-command path handles those.
    """
    members = []
    for pattern in patterns:
        if pattern.startswith("!"):
            continue
        for match in root.glob(pattern):
            if match.is_dir() and (match / "package.json").exists():
                members.append(match)
    return members


def detect_workspace_members(root: Path) -> list[Path]:
    """Detect npm/yarn workspace member directories declared in root's package.json.

    Returns an empty list if root has no package.json, no "workspaces"
    field, the detected package manager is pnpm (which declares workspaces
    in a separate pnpm-workspace.yaml, not handled here), or resolution
    fails for any reason -- callers should treat that as "not a workspace"
    and fall back to single-directory scanning, not surface an error.

    Args:
        root: Directory to check for a workspaces-declaring package.json

    Returns:
        Absolute paths to every resolved workspace member (root itself is
        not included -- callers decide whether to scan root too)
    """
    package_json = root / "package.json"
    if not package_json.exists():
        return []

    try:
        data = json.loads(package_json.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return []

    patterns = data.get("workspaces")
    if not patterns:
        return []
    if isinstance(patterns, dict):
        # npm/yarn also accept {"packages": [...]} form
        patterns = patterns.get("packages", [])
    if not patterns:
        return []

    package_manager, _ = detect_package_manager(root)
    if package_manager == "pnpm":
        return []

    # `not resolved` (not `is None`) deliberately treats an empty result the
    # same as a failure: npm/yarn's own workspace resolution depends on a
    # real `install` having populated node_modules/the lockfile -- on a
    # freshly cloned repo they report zero members even though patterns is
    # already confirmed non-empty above, so an empty list here is a signal
    # to fall back, not a trustworthy "genuinely no members".
    resolved = None
    if package_manager == "yarn":
        resolved = _resolve_via_yarn(root)
    if not resolved:
        resolved = _resolve_via_npm(root)
    if not resolved:
        resolved = _resolve_via_glob(root, patterns)

    seen: dict[Path, None] = {}
    for member in resolved:
        if member.is_dir():
            seen.setdefault(member.resolve(), None)
    return list(seen.keys())
