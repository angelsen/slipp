"""Server provisioning orchestration — order, poll, SSH setup, bootstrap."""

import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any


from slipp import output
from slipp.models.provision import ProvisionPhase, ProvisionState
from slipp.services.bootstrap import provision_account
from slipp.services.providers.gigahost import GigahostClient
from slipp.services.providers.state import ProvisionStateService
from slipp.utils.errors import ProvisionError

DEPLOY_POLL_INTERVAL = 5
DEPLOY_TIMEOUT = 3600
SSH_READY_TIMEOUT = 600
SSH_READY_INTERVAL = 1
STALE_THRESHOLD_HOURS = 24


def resolve_server(client: GigahostClient, name_or_ip: str) -> tuple[int, str, str]:
    """Resolve a server by name or primary IP.

    Returns:
        (srv_id, display_name, ip)
    """
    servers: list[dict[str, Any]] = client.list_servers()
    for s in servers:
        display = s.get("srv_name") or s.get("srv_hostname") or ""
        ip = s.get("srv_primary_ip") or ""
        if display == name_or_ip or ip == name_or_ip:
            return s["srv_id"], display or name_or_ip, ip

    raise ProvisionError(f"No server found matching '{name_or_ip}'")


def _find_key_id(account: dict[str, Any], name: str, pubkey: str) -> int | None:
    """Find an SSH key ID by name or key data in the account's sshkeys list."""
    for key in account.get("sshkeys", []):
        if key.get("key_data") == pubkey or key.get("key_name") == name:
            key_id = key.get("key_id") or key.get("id")
            if key_id is not None:
                return key_id
    return None


def find_ssh_public_key() -> Path:
    """Find local SSH public keys and let the user pick if multiple exist."""
    candidates = [
        p
        for name in ("id_ed25519.pub", "id_rsa.pub", "id_ecdsa.pub")
        if (p := Path.home() / ".ssh" / name).exists()
    ]
    if not candidates:
        raise ProvisionError(
            "No SSH public key found in ~/.ssh "
            "(looked for id_ed25519.pub, id_rsa.pub, id_ecdsa.pub)"
        )

    if len(candidates) == 1:
        output.info(f"SSH key: {candidates[0].name}")
        return candidates[0]

    rows = [{"#": i, "key": c.name} for i, c in enumerate(candidates, 1)]
    return output.pick(candidates, rows, "Available SSH keys")


def ensure_ssh_key(client: GigahostClient, name: str, pubkey_path: Path) -> int | None:
    """Upload the local SSH public key to the Gigahost account if not already present."""
    pubkey = pubkey_path.read_text().strip()

    existing = _find_key_id(client.get_account(), name, pubkey)
    if existing is not None:
        return existing

    client.add_ssh_key(name=name, public_key=pubkey)

    return _find_key_id(client.get_account(), name, pubkey)


def select_product(client: GigahostClient) -> tuple[int, int, int]:
    """Show the deployable catalog and let the user pick product + region.

    Returns:
        (product_id, price_id, region_id)
    """
    catalog = client.get_catalog()
    tiers: list[dict[str, Any]] = catalog.get("tiers", [])
    regions: list[dict[str, Any]] = catalog.get("regions", [])

    products = [
        p for tier in tiers for p in tier.get("products", []) if p.get("in_stock")
    ]
    if not products:
        raise ProvisionError("No products in stock")
    if not regions:
        raise ProvisionError("No regions available")

    product_rows = [
        {
            "#": i,
            "name": p.get("product_name"),
            "cores": p.get("vm_cores"),
            "ram_mb": p.get("vm_memory"),
            "disk_gb": p.get("vm_storage"),
            "monthly": p.get("rate_monthly"),
        }
        for i, p in enumerate(products, 1)
    ]
    product = output.pick(products, product_rows, "Available products")

    region_rows = [
        {"#": i, "region": r.get("region_name")} for i, r in enumerate(regions, 1)
    ]
    region = output.pick(regions, region_rows, "Available regions")

    return product["product_id"], product["price_id"], region["region_id"]


def select_os(client: GigahostClient) -> int:
    """Pick a distro and OS version interactively, defaulting to latest Debian."""
    distros = client.list_distros()
    if not distros:
        raise ProvisionError("No distributions available")

    debian_idx = next(
        (
            i
            for i, d in enumerate(distros)
            if "debian" in str(d.get("dist_name", "")).lower()
        ),
        0,
    )

    distro_rows = [
        {"#": i, "name": d.get("dist_name")} for i, d in enumerate(distros, 1)
    ]
    chosen_distro = output.pick(
        distros, distro_rows, "Available distributions", default=debian_idx + 1
    )

    versions = client.list_os_versions(chosen_distro["dist_id"])
    if not versions:
        raise ProvisionError(
            f"No OS versions available for {chosen_distro.get('dist_name')}"
        )

    version_rows = [
        {"#": i, "name": v.get("os_name"), "arch": v.get("os_arch")}
        for i, v in enumerate(versions, 1)
    ]
    chosen_version = output.pick(
        versions, version_rows, "Available OS versions", default=len(versions)
    )

    return chosen_version["os_id"]


def poll_deploy_status(client: GigahostClient, order_ids: list[int]) -> dict[str, Any]:
    """Poll GET /deploy/status until all servers are ready."""
    output.warning("Server installation can take up to 60 minutes")
    output.hint("Ctrl+C to cancel — re-run the same command to resume")
    elapsed = 0
    with output.spinner("Provisioning server...") as update:
        while elapsed < DEPLOY_TIMEOUT:
            status = client.get_deploy_status(order_ids)
            servers = status.get("servers", [])
            if servers:
                update(servers[0].get("status", "waiting"))
            if status.get("all_ready"):
                return servers[0]
            time.sleep(DEPLOY_POLL_INTERVAL)
            elapsed += DEPLOY_POLL_INTERVAL

    raise ProvisionError(
        f"Deploy timed out after {DEPLOY_TIMEOUT}s -- check status in Gigahost panel"
    )


def wait_for_ssh(host: str, *, started_at: datetime | None = None) -> None:
    """Poll until SSH accepts connections, adding host key to known_hosts."""
    output.hint("Ctrl+C to cancel — re-run the same command to resume")
    t0 = time.monotonic()
    epoch = started_at or datetime.now()
    with output.spinner("Waiting for SSH...") as update:
        while time.monotonic() - t0 < SSH_READY_TIMEOUT:
            elapsed = int((datetime.now() - epoch).total_seconds())
            try:
                with socket.create_connection((host, 22), timeout=3):
                    pass
                update("port open, scanning host key...")
                subprocess.run(
                    ["ssh-keygen", "-R", host],
                    capture_output=True,
                )
                scan = subprocess.run(
                    ["ssh-keyscan", "-H", host],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if scan.stdout.strip():
                    with open(Path.home() / ".ssh" / "known_hosts", "a") as f:
                        f.write(scan.stdout)
                return
            except (OSError, subprocess.TimeoutExpired):
                update(f"waiting ({elapsed}s)")
                time.sleep(SSH_READY_INTERVAL)

    raise ProvisionError(f"SSH not reachable after {SSH_READY_TIMEOUT}s on {host}:22")


def provision_server(client: GigahostClient, name: str) -> tuple[str, int]:
    """Order a VPS via Gigahost and poll until it's ready to accept SSH.

    Returns:
        (ip_address, srv_id)
    """
    product_id, price_id, region_id = select_product(client)
    os_id = select_os(client)

    pubkey_path = find_ssh_public_key()
    key_id = ensure_ssh_key(client, f"slipp-{name}", pubkey_path)

    state = ProvisionState(name=name)
    ProvisionStateService.save(state)

    output.info("Ordering server...")
    order_ids = client.deploy_server(
        product_id=product_id,
        price_id=price_id,
        region_id=region_id,
        os_id=os_id,
        hostnames=[name],
        ssh_keys=[key_id] if key_id else None,
    )

    state = state.model_copy(update={"order_ids": order_ids})
    ProvisionStateService.save(state)

    return _poll_and_wait(client, state)


def _poll_and_wait(client: GigahostClient, state: ProvisionState) -> tuple[str, int]:
    """Poll for server readiness, save provisioned state, wait for SSH."""
    if not state.order_ids:
        raise ProvisionError("Cannot poll deploy status without order IDs")
    server = poll_deploy_status(client, state.order_ids)
    ip = server.get("ip")
    srv_id = server.get("srv_id")
    if not ip or not srv_id:
        raise ProvisionError("Deploy completed but no IP/server ID was returned")

    ProvisionStateService.save(
        state.model_copy(
            update={
                "ip": ip,
                "srv_id": srv_id,
                "phase": ProvisionPhase.PROVISIONED,
            }
        )
    )

    wait_for_ssh(ip, started_at=state.created_at)
    return ip, srv_id


def _warn_if_stale(created_at: datetime) -> None:
    """Warn when resuming a saved provision/install state that's grown old."""
    age = datetime.now() - created_at
    if age.total_seconds() > STALE_THRESHOLD_HOURS * 3600:
        output.warning(
            f"This provision was started {age.days}d {age.seconds // 3600}h ago"
        )


def _resume_provision(client: GigahostClient, state: ProvisionState) -> tuple[str, int]:
    """Resume a previously started provision from its saved phase."""
    _warn_if_stale(state.created_at)

    if state.phase == ProvisionPhase.ORDERED:
        output.info(f"Polling for server readiness (order {state.order_ids})...")
        return _poll_and_wait(client, state)

    if state.phase == ProvisionPhase.PROVISIONED:
        if state.ip is None or state.srv_id is None:
            raise ProvisionError(
                f"Provision state for '{state.name}' is missing ip or srv_id"
            )
        output.info(f"Server {state.ip} already provisioned, checking SSH...")
        wait_for_ssh(state.ip, started_at=state.created_at)
        return state.ip, state.srv_id

    if state.phase == ProvisionPhase.INSTALLING:
        raise ProvisionError(
            f"Server '{state.name}' is mid-install — "
            f"resume with 'slipp server install {state.name}'"
        )

    raise ProvisionError(f"Unexpected provision phase: {state.phase}")


def provision_and_bootstrap(client: GigahostClient, name: str) -> tuple[str, int]:
    """Provision a VPS and bootstrap the SSH user.

    Resumes from saved state if an in-progress provision exists for this name.

    Returns:
        (ip_address, srv_id)
    """
    state = ProvisionStateService.load(name)

    if state:
        output.info(
            f"Resuming provision for '{name}' "
            f"(phase: {state.phase}, started: {state.created_at:%Y-%m-%d %H:%M})"
        )
        ip, srv_id = _resume_provision(client, state)
    else:
        ip, srv_id = provision_server(client, name)

    # _resume_provision/provision_server already waited for SSH above.
    return _bootstrap_user(ip, srv_id, name)


def _wait_and_bootstrap(
    ip: str, srv_id: int, name: str, *, started_at: datetime | None = None
) -> tuple[str, int]:
    """Wait for SSH, bootstrap slipp user, clean up state file."""
    wait_for_ssh(ip, started_at=started_at)
    return _bootstrap_user(ip, srv_id, name)


def _bootstrap_user(ip: str, srv_id: int, name: str) -> tuple[str, int]:
    """Bootstrap the slipp user and clean up state file (SSH already confirmed ready)."""
    output.success(f"Server ready: {ip}")
    output.info("Bootstrapping SSH user...")
    provision_account(ip, "root", None, 22, "slipp", dry_run=False)
    ProvisionStateService.delete(name)
    return ip, srv_id


def install_server(
    client: GigahostClient, name_or_ip: str, *, force: bool = False
) -> tuple[str, int] | None:
    """Reinstall OS on an existing server and bootstrap the slipp user."""
    srv_id, display, ip = resolve_server(client, name_or_ip)

    state = ProvisionStateService.load(display)
    if state and state.phase == ProvisionPhase.INSTALLING:
        output.info(
            f"Resuming install for '{display}' "
            f"(started: {state.created_at:%Y-%m-%d %H:%M})"
        )
        _warn_if_stale(state.created_at)
        return _wait_and_bootstrap(ip, srv_id, display, started_at=state.created_at)

    if not force:
        if not output.confirm(f"Wipe and reinstall '{display}' ({ip})?", default=False):
            output.info("Cancelled")
            return None

    os_id = select_os(client)
    pubkey_path = find_ssh_public_key()
    key_id = ensure_ssh_key(client, f"slipp-{display}", pubkey_path)

    now = datetime.now()
    ProvisionStateService.save(
        ProvisionState(
            name=display,
            srv_id=srv_id,
            ip=ip,
            phase=ProvisionPhase.INSTALLING,
            created_at=now,
        )
    )

    output.info("Reinstalling server...")
    client.reinstall_server(srv_id, os_id, hostname=display, key_id=key_id)

    return _wait_and_bootstrap(ip, srv_id, display, started_at=now)
