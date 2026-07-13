"""wg-manage SSH orchestration and exposure sync.

Business logic for talking to a wg-manage hub over SSH: fetching/removing
services, and converging exposure against a project's declared services.
Two independent consumers -- commands/resources.py (sync/list/remove CLI
surface) and commands/deploy.py (post-deploy stray-cleanup hook) -- share
this instead of one command module importing from another, per this
project's commands = args -> service -> output layering.
"""

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

from slipp import output
from slipp.models.deployment import DeploymentHostConfig, DetectedService
from slipp.models.local_config import ExposeEntry
from slipp.scanner import scan
from slipp.scanner.routing import default_expose, validate_expose
from slipp.services.ssh import SSHResult, SSHService
from slipp.utils.errors import WgManageError
from slipp.utils.network import is_ip_address


def service_label(project_name: str) -> str:
    """The wg-manage service label slipp stamps on everything it exposes.

    Single definition for the "slipp:<project_name>" format -- used here
    for remove/sync attribution filtering, and by
    services/launch/stages/wg_manage.py to pass the same label into the
    wg-manage-exposure Ansible role template, so the label the role
    writes and the label sync/remove filter on can never drift apart.
    """
    return f"slipp:{project_name}"


def build_wg_services(
    services: list[DetectedService],
    domain: str,
    expose: dict[str, ExposeEntry] | None = None,
) -> list[dict]:
    """Build wg-manage service exposure entries from the expose: block.

    Translates the shared routing block (same one build_caddy_sites
    consumes) onto wg-manage's one-FQDN-to-one-entry model: per domain,
    the service on path "/" owns the entry, and every other path on that
    domain is folded in as a `--route 'PATH/*=localhost:PORT'` flag.

    Args:
        services: Detected services (supply the ports).
        domain: Application domain, used to seed the default routing when
            no expose block is given.
        expose: Explicit routing (service name -> domain/path). Defaults
            to the frontend/backend convention via default_expose().

    Returns:
        List of {name, fqdn, port, route_flags} dicts. route_flags is a
        pre-joined string of `--route` flags (empty when there are none) --
        the two consumers (sync(), which only reads fqdn, and the Ansible
        role template, which needs the flag string verbatim) have no use
        for anything more structured.

    Raises:
        WgManageError: If the domain is an IP address or the expose block
            is invalid (see validate_expose).
    """
    if is_ip_address(domain):
        raise WgManageError(
            f"wg-manage routes by FQDN; app_domain '{domain}' is an IP address. "
            "Set a real domain on the inventory host."
        )

    if expose is None:
        expose = default_expose(services, domain)

    try:
        validate_expose(expose, services)
    except ValueError as e:
        raise WgManageError(str(e)) from e

    ports = {s.name: s.port for s in services}
    by_domain: dict[str, list[tuple[str, ExposeEntry]]] = {}
    for name, entry in expose.items():
        by_domain.setdefault(entry.domain, []).append((name, entry))

    entries = []
    for fqdn, items in by_domain.items():
        # validate_expose guarantees exactly one "/" entry per domain.
        root = next(n for n, e in items if e.path == "/")
        # ExposeEntry's validator normalizes paths (leading /, no trailing).
        route_flags = " ".join(
            f"--route {shlex.quote(f'{e.path}/*=localhost:{ports[n]}')}"
            for n, e in items
            if e.path != "/"
        )
        entries.append(
            {
                "name": root,
                "fqdn": fqdn,
                "port": ports[root],
                "route_flags": route_flags,
            }
        )

    return entries


def make_hub(name: str, ip: str, repo_path: Path) -> None:
    """Hub-ify a host by running wg-deploy's scripts/new-host.sh against it.

    Interactive: ansible-vault may prompt for the vault password (no
    stdout/stderr capture, so the prompt reaches the terminal).

    Raises:
        WgManageError: If new-host.sh exits non-zero, or the configured
            repo path has gone stale (moved/deleted since `providers add
            wg-deploy` validated it) and can't be used as a cwd.
    """
    try:
        result = subprocess.run(
            ["bash", "scripts/new-host.sh", name, ip],
            cwd=repo_path,
        )
    except OSError as e:
        raise WgManageError(f"Cannot run new-host.sh in {repo_path}: {e}") from e
    if result.returncode != 0:
        raise WgManageError(f"new-host.sh failed (exit {result.returncode})")


def _ssh_exec(host: DeploymentHostConfig, cmd: str) -> SSHResult:
    """Run `cmd` on `host` over SSH, converting connection failures to WgManageError.

    Single connect-execute-disconnect per call -- every wg-manage operation
    here is one-command, so a fresh connection per call is simpler than
    threading a shared session through and costs nothing extra at this
    scale.

    Raises:
        WgManageError: On connection failure. A non-zero *remote* exit is
            not raised here -- callers inspect result.ok themselves, since
            some treat it as fatal and others (stray removal) as a
            per-item warning that shouldn't abort the rest of the batch.
    """
    try:
        with SSHService(host) as ssh:
            return ssh.execute(cmd)
    except Exception as e:
        raise WgManageError(f"Failed to connect to {host.ansible_host}: {e}") from e


def fetch_services(host: DeploymentHostConfig) -> list[dict[str, Any]]:
    """SSH into `host` and return its wg-manage service registry.

    Raises:
        WgManageError: On connection failure, non-zero exit, or unparsable
            JSON.
    """
    result = _ssh_exec(host, "wg-manage service list --json")

    if not result.ok:
        raise WgManageError(
            f"wg-manage service list failed: {result.stderr.strip() or result.stdout.strip()}"
        )

    try:
        return json.loads(result.stdout).get("services", [])
    except json.JSONDecodeError as e:
        raise WgManageError(f"Failed to parse wg-manage output: {e}") from e


def remove_service(host: DeploymentHostConfig, project_name: str, name: str) -> None:
    """Remove a wg-manage service, refusing if it isn't labeled to this project.

    Raises:
        WgManageError: If the service doesn't exist, isn't labeled to
            `project_name`, or the SSH round-trip fails.
    """
    label = service_label(project_name)
    services = fetch_services(host)
    match = next((s for s in services if s.get("name") == name), None)
    if not match:
        raise WgManageError(f"wg-manage service '{name}' not found")

    if match.get("label") != label:
        raise WgManageError(
            f"'{name}' isn't labeled to this project "
            f"(label: {match.get('label') or 'none'}, expected: {label}) -- refusing to remove"
        )

    result = _ssh_exec(host, f"wg-manage service rm {shlex.quote(name)}")
    if not result.ok:
        raise WgManageError(
            f"Failed to remove '{name}': {result.stderr.strip() or result.stdout.strip()}"
        )


def sync(
    dirs: list[Path],
    project_name: str,
    host: DeploymentHostConfig,
    *,
    expose: dict[str, ExposeEntry] | None = None,
    dry_run: bool = False,
    quiet: bool = False,
) -> None:
    """Converge wg-manage's registry on `host` to this project's declared services.

    Removal-only converge: entries labeled "slipp:<project_name>" that
    this project no longer declares are removed. Adds/updates aren't this
    function's job -- the wg-manage-exposure Ansible role (run at deploy)
    owns those; this only cleans up strays a rename/removal left behind.
    Never touches entries labeled to a different project, or unlabeled
    (hand-added) entries -- the label filter *is* the scoping rule.

    Args:
        dirs: Project source directories to scan for declared services
            (caller has already resolved --dir / workspace auto-detection
            -- this function only does scanning + converge, not CLI-arg
            interpretation).
        expose: The project's slipp.yaml expose: block, if any -- the
            declared FQDN set is derived from it so hand-edited routing
            isn't pruned as stray. None falls back to the default
            convention over the scanned services.
        quiet: Skip the routine "declared/kept" report -- the post-deploy
            hook passes this so a normal deploy with nothing to prune
            doesn't add noise. Strays (found or removed) are always
            reported regardless of this flag.

    Raises:
        WgManageError: If app_domain is missing, scanning fails, no
            services are detected, or the SSH round-trip fails. Callers
            that must not let this abort their own flow (the deploy hook)
            catch it.
    """
    app_domain = host.app_domain
    if not app_domain:
        raise WgManageError(
            f"No app_domain configured on inventory host '{host.inventory_hostname}'"
        )

    try:
        services = [s for s in (scan(d) for d in dirs) if s]
    except Exception as e:
        raise WgManageError(f"Failed to scan project: {e}") from e

    if not services:
        raise WgManageError("No services detected -- nothing to converge")

    declared = build_wg_services(services, app_domain, expose)
    declared_fqdns = {svc["fqdn"] for svc in declared}

    label = service_label(project_name)
    remote = fetch_services(host)
    labeled = [s for s in remote if s.get("label") == label]
    strays = [s for s in labeled if s.get("name") not in declared_fqdns]

    if not quiet:
        output.info(f"Declared: {', '.join(sorted(declared_fqdns))}")
        kept = [s for s in labeled if s.get("name") in declared_fqdns]
        if kept:
            output.success(
                f"Kept {len(kept)} service(s): {', '.join(s.get('name', '?') for s in kept)}"
            )

    if not strays:
        if not quiet:
            output.info("No stray services to remove")
        return

    if dry_run:
        output.warning(f"Would remove {len(strays)} stray service(s):")
        output.list_items([s.get("name", "?") for s in strays], indent=2)
        return

    for s in strays:
        name = s.get("name", "?")
        rm_result = _ssh_exec(host, f"wg-manage service rm {shlex.quote(name)}")
        if rm_result.ok:
            output.success(f"Removed stray wg-manage service: {name}")
        else:
            output.error(
                f"Failed to remove stray '{name}': "
                f"{rm_result.stderr.strip() or rm_result.stdout.strip()}"
            )
