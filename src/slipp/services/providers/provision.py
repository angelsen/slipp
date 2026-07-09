"""Server provisioning orchestration — order, poll, SSH setup, bootstrap."""

import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import typer

from slipp import output
from slipp.models.provision import ProvisionPhase, ProvisionState
from slipp.services.bootstrap import provision_account
from slipp.services.providers.gigahost import GigahostClient
from slipp.services.providers.state import ProvisionStateService
from slipp.utils.errors import ProvisionError

DEPLOY_POLL_INTERVAL = 5
DEPLOY_TIMEOUT = 3600
SSH_READY_TIMEOUT = 120
SSH_READY_INTERVAL = 5
STALE_THRESHOLD_HOURS = 24


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

    output.task("Available SSH keys")
    output.table([{"#": i, "key": c.name} for i, c in enumerate(candidates, 1)])
    choice = typer.prompt("Pick an SSH key", type=int, default=1)
    return candidates[max(1, min(choice, len(candidates))) - 1]


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

    output.task("Available products")
    output.table(
        [
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
    )
    choice = typer.prompt("Pick a product", type=int, default=1)
    product = products[max(1, min(choice, len(products))) - 1]

    output.task("Available regions")
    output.table(
        [{"#": i, "region": r.get("region_name")} for i, r in enumerate(regions, 1)]
    )
    region_choice = typer.prompt("Pick a region", type=int, default=1)
    region = regions[max(1, min(region_choice, len(regions))) - 1]

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

    output.task("Available distributions")
    output.table(
        [{"#": i, "name": d.get("dist_name")} for i, d in enumerate(distros, 1)]
    )
    choice = typer.prompt("Pick a distribution", type=int, default=debian_idx + 1)
    chosen_distro = distros[max(1, min(choice, len(distros))) - 1]

    versions = client.list_os_versions(chosen_distro["dist_id"])
    if not versions:
        raise ProvisionError(
            f"No OS versions available for {chosen_distro.get('dist_name')}"
        )

    output.task("Available OS versions")
    output.table(
        [
            {"#": i, "name": v.get("os_name"), "arch": v.get("os_arch")}
            for i, v in enumerate(versions, 1)
        ]
    )
    ver_choice = typer.prompt("Pick a version", type=int, default=len(versions))
    chosen_version = versions[max(1, min(ver_choice, len(versions))) - 1]

    return chosen_version["os_id"]


def poll_deploy_status(client: GigahostClient, order_ids: list[int]) -> dict[str, Any]:
    """Poll GET /deploy/status until all servers are ready."""
    output.warning("Server installation can take up to 60 minutes")
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


def wait_for_ssh(host: str) -> None:
    """Poll until SSH accepts connections, adding host key to known_hosts."""
    elapsed = 0
    with output.spinner("Waiting for SSH...") as update:
        while elapsed < SSH_READY_TIMEOUT:
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
                elapsed += SSH_READY_INTERVAL

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

    output.info("Ordering server...")
    order_ids = client.deploy_server(
        product_id=product_id,
        price_id=price_id,
        region_id=region_id,
        os_id=os_id,
        hostnames=[name],
        ssh_keys=[key_id] if key_id else None,
    )

    state = ProvisionState(name=name, order_ids=order_ids)
    ProvisionStateService.save(state)

    return _poll_and_wait(client, state)


def _poll_and_wait(client: GigahostClient, state: ProvisionState) -> tuple[str, int]:
    """Poll for server readiness, save provisioned state, wait for SSH."""
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
                "updated_at": datetime.now(),
            }
        )
    )

    wait_for_ssh(ip)
    return ip, srv_id


def _resume_provision(client: GigahostClient, state: ProvisionState) -> tuple[str, int]:
    """Resume a previously started provision from its saved phase."""
    age = datetime.now() - state.created_at
    if age.total_seconds() > STALE_THRESHOLD_HOURS * 3600:
        output.warning(
            f"This provision was started {age.days}d {age.seconds // 3600}h ago"
        )

    if state.phase == ProvisionPhase.ORDERED:
        output.info(f"Polling for server readiness (order {state.order_ids})...")
        return _poll_and_wait(client, state)

    if state.phase == ProvisionPhase.PROVISIONED:
        if state.ip is None or state.srv_id is None:
            raise ProvisionError(
                f"Provision state for '{state.name}' is missing ip or srv_id"
            )
        output.info(f"Server {state.ip} already provisioned, checking SSH...")
        wait_for_ssh(state.ip)
        return state.ip, state.srv_id

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

    output.success(f"Server ready: {ip}")

    output.info("Bootstrapping SSH user...")
    provision_account(ip, "root", None, 22, "slipp", dry_run=False)

    ProvisionStateService.delete(name)
    return ip, srv_id
