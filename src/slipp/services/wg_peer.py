"""WireGuard peer bootstrap orchestration for `--proxy wg-manage` secondary hosts.

Mirrors services/run/caddy.py's CaddyProxy shape: a live SSH probe decides
whether bootstrap work is needed at all (no persisted cache field), and
the actual work runs a bundled Ansible playbook (slipp.playbooks.wg_peer)
against an ad-hoc single-host inventory -- same pattern
CaddyProxy.ensure_installed() uses for slipp.playbooks.caddy_dev.

Automates, end to end, the manual steps proven live this session: `wg-manage
add <peer>` on the hub -> nmcli/wg-quick on the peer -> a scoped firewall
rule -> (elsewhere) `wg-manage service add` targeting the peer name.
"""

import re
import shlex
from importlib.resources import files
from pathlib import Path

from slipp.models.deployment import DeploymentHostConfig
from slipp.services.ansible import append_log_hint, run_playbook_with_spinner
from slipp.services.ssh import SSHService
from slipp.services.wg_manage import ssh_exec
from slipp.utils.errors import WgManageError
from slipp.utils.files import get_log_dir, temp_secret_file


def _iface_name(hub: DeploymentHostConfig) -> str:
    """WireGuard interface name for a peer's tunnel to `hub`.

    Named after the hub's own inventory_hostname (matching this session's
    manual `nmcli`/`wg-quick` convention) rather than a fixed `wg0` -- a
    host that's a peer of two different hubs needs two distinct
    interfaces, and inventory_hostname is already guaranteed unique per
    hub within one slipp project.
    """
    return hub.inventory_hostname


def _get_playbook_path() -> Path:
    """Locate the bundled wg_peer playbook.

    Raises:
        WgManageError: If the playbook can't be found.
    """
    try:
        playbook_dir = files("slipp.playbooks.wg_peer")
        playbook_path = Path(str(playbook_dir.joinpath("playbook.yml")))

        if not playbook_path.exists():
            raise WgManageError(f"Playbook not found: {playbook_path}")

        return playbook_path
    except WgManageError:
        raise
    except Exception as e:
        raise WgManageError(f"Failed to locate bundled wg_peer playbook: {e}") from e


def is_bootstrapped(
    hub: DeploymentHostConfig, peer: DeploymentHostConfig, ports: list[int]
) -> bool:
    """Whether `peer` already has a working WireGuard tunnel to `hub` for every port in `ports`.

    A live compound SSH probe against `peer` (no persisted cache field --
    same one-shot-compound-command shape as CaddyProxy.is_installed()):
    1. `wg-quick@<iface>` (iface named after `hub`) is active
    2. The peer's own WireGuard config has a [Peer] stanza written (a
       proxy for "bootstrap has run for this hub" -- the exact keys
       aren't re-verified against the hub, since wg-manage's `add` can't
       be safely re-run to check: it hard-errors if the peer already
       exists, so re-probing the hub itself to compare keys would risk
       the same failure this check exists to avoid)
    3. A `ufw` ALLOW rule exists for every port in `ports`

    `ports` is every port currently assigned to `peer` (not just one
    service) -- a True result here means ensure_peer() can skip *all*
    work, tunnel and firewall alike. A False result doesn't by itself
    mean a full bootstrap is needed, though -- see _tunnel_active(),
    which ensure_peer() uses to tell "peer never bootstrapped" apart from
    "peer's tunnel is fine, a newly assigned port just needs its own
    firewall rule."

    Raises:
        SSHConnectionError, SSHAuthenticationError: `peer` unreachable.
    """
    iface = _iface_name(hub)
    port_checks = " && ".join(
        f"ufw status | grep -qE '^{port}/tcp[[:space:]]+ALLOW'" for port in ports
    )
    check_cmd = f"{_TUNNEL_ACTIVE_CMD.format(iface=iface)}" + (
        f" && {port_checks}" if port_checks else ""
    )
    with SSHService(peer) as ssh:
        ssh.ensure_sudo(
            f"Checking wg-manage peer bootstrap status on {peer.ansible_host}"
        )
        return ssh.execute(f"sudo sh -c {shlex.quote(check_cmd)}").ok


_TUNNEL_ACTIVE_CMD = (
    "systemctl is-active wg-quick@{iface} 2>/dev/null | grep -qx active && "
    "grep -q '^\\[Peer\\]' /etc/wireguard/{iface}.conf 2>/dev/null"
)


def _tunnel_active(hub: DeploymentHostConfig, peer: DeploymentHostConfig) -> bool:
    """Whether `peer`'s WireGuard tunnel to `hub` is up, independent of any port.

    The port-independent half of is_bootstrapped()'s own check (same two
    conditions, minus the ufw port loop) -- used by ensure_peer() to tell
    "never bootstrapped, needs the full wg-manage add + tunnel setup"
    apart from "tunnel's fine, a newly assigned port just needs its own
    firewall rule."

    Raises:
        SSHConnectionError, SSHAuthenticationError: `peer` unreachable.
    """
    iface = _iface_name(hub)
    check_cmd = _TUNNEL_ACTIVE_CMD.format(iface=iface)
    with SSHService(peer) as ssh:
        ssh.ensure_sudo(f"Checking WireGuard tunnel status on {peer.ansible_host}")
        return ssh.execute(f"sudo sh -c {shlex.quote(check_cmd)}").ok


def _hub_wg_ip(hub: DeploymentHostConfig) -> str:
    """The hub's own WireGuard tunnel IP, read directly off its wg0 interface.

    Not exposed by any wg-manage CLI command (confirmed live: `wg-manage
    list --json`/`status --json` cover peers and services, never the
    hub's own address) -- normally only ever seen as a side effect of
    `wg-manage add <peer>`'s one-time client-config output (its `DNS =`
    line). ensure_peer() can't re-trigger that for an already-registered
    peer (wg-manage add fails "already exists"), so a peer that needs a
    new port opened later needs another way to learn it. Reading it
    straight off the interface works regardless of bootstrap state and
    needs no wg-manage-side changes -- "wg0" is wg-manage's own fixed
    interface name (confirmed in wg-deploy/templates/wg-manage.py.j2,
    not something slipp chooses or that varies per hub).

    Raises:
        WgManageError: If the hub SSH round-trip fails or the IP can't be
            parsed from the interface's own address.
    """
    result = ssh_exec(hub, "ip -4 -o addr show wg0")
    if not result.ok:
        raise WgManageError(
            f"Could not read {hub.ansible_host}'s WireGuard tunnel IP "
            f"(is it actually a wg-manage hub?): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", result.stdout)
    if not match:
        raise WgManageError(
            f"Could not parse a WireGuard tunnel IP from `ip addr show wg0` "
            f"on {hub.ansible_host}: {result.stdout!r}"
        )
    return match.group(1)


def _run_wg_peer_playbook(
    peer: DeploymentHostConfig,
    extra_vars: dict[str, object],
    *,
    label: str,
    error_label: str,
    tags: str | None = None,
) -> None:
    """Run the bundled wg_peer playbook against `peer`, raising on failure.

    Shared by ensure_peer()'s full bootstrap path and _open_ports()'s
    incremental one -- both need the same ad-hoc single-host inventory,
    spinner-wrapped run, and exit-code-to-WgManageError translation, and
    differ only in extra_vars/tags. The full path additionally wraps a
    second temp_secret_file for the peer's WireGuard config (carries a
    private key, so it's kept at that call site rather than threaded
    through here as a parameter).

    Raises:
        WgManageError: If the playbook run exits non-zero.
    """
    playbook_path = _get_playbook_path()
    inventory_content = f"[all]\n{peer.to_ini_line()}\n"

    with temp_secret_file(
        inventory_content, prefix="slipp-wgpeer-inv-", suffix=".ini"
    ) as inventory_path:
        run_result = run_playbook_with_spinner(
            str(playbook_path),
            str(inventory_path),
            label=label,
            extra_vars=extra_vars,
            tags=tags,
            log_dir=get_log_dir(),
        )

        if run_result.exit_code != 0:
            message = append_log_hint(
                f"{error_label} (exit code {run_result.exit_code})", run_result
            )
            raise WgManageError(message)


def _open_ports(
    hub: DeploymentHostConfig, peer: DeploymentHostConfig, ports: list[int]
) -> None:
    """Open firewall exceptions for `ports` on an already-bootstrapped `peer`.

    The incremental path: no wg-manage add, no key/config work, no
    tunnel restart -- just re-runs the bundled playbook's `firewall`-
    tagged tasks (idempotent per port; already-open ports are a no-op).
    Only called once _tunnel_active() has confirmed the tunnel itself
    needs no work.

    Raises:
        WgManageError: If the hub's WireGuard IP can't be read, or the
            firewall-tagged playbook run fails.
    """
    peer_name = peer.inventory_hostname
    _run_wg_peer_playbook(
        peer,
        {"hub_wg_ip": _hub_wg_ip(hub), "service_ports": ports},
        label=f"Opening new port(s) for WireGuard peer {peer_name}",
        error_label=f"Opening new port(s) failed for peer '{peer_name}'",
        tags="firewall",
    )


def ensure_peer(
    hub: DeploymentHostConfig, peer: DeploymentHostConfig, ports: list[int]
) -> None:
    """Bootstrap `peer` as a WireGuard peer of `hub`, idempotently and incrementally.

    `ports` is every port currently assigned to `peer`. Three outcomes,
    checked cheapest/most-common first:

    1. is_bootstrapped() is already True for the full current port set:
       no-op -- no new peer on the hub, no key regeneration, no duplicate
       firewall rule.
    2. Otherwise, if _tunnel_active() is True (the tunnel itself is fine,
       just a newly assigned port needs its own rule): _open_ports()
       re-runs only the playbook's `firewall`-tagged tasks against the
       full current port set (idempotent -- already-open ports are a
       no-op). No wg-manage add, no key/config work.
    3. Otherwise (peer never bootstrapped at all): the full path --
       a. SSHes to `hub` and runs `wg-manage add <peer.inventory_hostname>`,
          capturing the printed client config. This must happen before the
          generated playbook's `wg-manage service add <peer>:<port>` call --
          resolve_target() resolves the peer name eagerly, at add-time, so
          the peer must already exist on the hub by then.
       b. Parses the hub's own WireGuard tunnel IP out of the captured
          config's `DNS = ` line.
       c. Runs the bundled wg_peer playbook's `tunnel` + `firewall` tasks
          against `peer` directly (an ad-hoc single-host inventory,
          mirroring CaddyProxy.ensure_installed()) to install WireGuard,
          write the config, bring up the tunnel, and open the scoped
          `ufw` rules.

    Raises:
        WgManageError: If the hub SSH round-trip fails, the peer is
            registered on the hub but its tunnel never came up (a prior
            partial failure -- needs manual reconciliation, see the
            raised message), the hub's output couldn't be parsed, or the
            bootstrap/firewall playbook run fails.
    """
    if is_bootstrapped(hub, peer, ports):
        return

    if _tunnel_active(hub, peer):
        _open_ports(hub, peer, ports)
        return

    peer_name = peer.inventory_hostname
    result = ssh_exec(hub, f"wg-manage add {shlex.quote(peer_name)}")
    if not result.ok:
        detail = result.stderr.strip() or result.stdout.strip()
        if "already exists" in detail:
            # wg-manage add has no create-or-update semantics (unlike
            # `service add`) and can't reissue an already-issued peer's
            # private key. _tunnel_active() already ruled out "tunnel's
            # fine, just needs a new port rule" above, so landing here
            # means the peer is registered on the hub but its tunnel
            # never actually came up -- a previous run that registered
            # the peer but failed before finishing peer-side setup.
            # Auto-recovery isn't safely possible without reissuing keys;
            # surface the fix instead of a raw wg-manage error dump.
            raise WgManageError(
                f"wg-manage on {hub.ansible_host} already has a peer named "
                f"'{peer_name}', but its tunnel to {peer.ansible_host} isn't "
                "up -- likely a previous deploy that failed mid-bootstrap. "
                "wg-manage can't reissue an existing peer's private key to "
                "recover automatically. SSH to the peer and check "
                f"`wg show {_iface_name(hub)}` against what's expected; "
                f"otherwise run `wg-manage rotate {peer_name}` on the hub "
                "and re-provision the peer."
            )
        raise WgManageError(f"wg-manage add {peer_name} failed: {detail}")

    peer_config = result.stdout
    hub_wg_ip_match = re.search(r"^DNS\s*=\s*(\S+)", peer_config, re.MULTILINE)
    if not hub_wg_ip_match:
        raise WgManageError(
            f"Could not parse the hub's WireGuard IP from `wg-manage add "
            f"{peer_name}`'s output -- expected a 'DNS = <ip>' line in the "
            "printed client config."
        )
    hub_wg_ip = hub_wg_ip_match.group(1)

    # wg-quick invokes resolvconf(8)/openresolv for any [Interface] DNS=
    # line -- not installed by default on a fresh peer host, and wg-quick
    # rolls the whole interface back on any script step failing, so a
    # missing resolvconf binary silently kills the entire tunnel instead
    # of just DNS. This peer only needs tunnel routing to reach the hub,
    # not the hub's DNS server for its own resolution -- strip the line
    # rather than adding a resolvconf dependency purely to satisfy
    # something this bootstrap doesn't actually need.
    iface_config = re.sub(r"^DNS\s*=.*\n?", "", peer_config, flags=re.MULTILINE)

    # The captured config carries a WireGuard private key -- passed to the
    # playbook by file path (read via lookup('file', ...) on the control
    # node), never as a literal -e extra-var value, which would land in
    # the ansible-playbook argv and be visible to any local user via `ps`.
    with temp_secret_file(
        iface_config, prefix="slipp-wgpeer-conf-", suffix=".conf"
    ) as config_path:
        extra_vars = {
            "peer_config_path": str(config_path),
            "iface_name": _iface_name(hub),
            "hub_wg_ip": hub_wg_ip,
            "service_ports": ports,
        }
        _run_wg_peer_playbook(
            peer,
            extra_vars,
            label=f"Bootstrapping WireGuard peer {peer_name}",
            error_label=f"WireGuard peer bootstrap failed for '{peer_name}'",
        )
