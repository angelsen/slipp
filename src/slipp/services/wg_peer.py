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
    service) -- ensure_peer() bootstraps all of a peer's ports in a
    single run, so re-checking all of them here is what makes a later,
    unchanged re-deploy correctly skip the whole bootstrap. (Known gap:
    adding a *new* service to an already-bootstrapped peer later will
    make this return False again, and ensure_peer() will then hit
    wg-manage's "peer already exists" error rather than incrementally
    opening just the new port -- see ensure_peer()'s docstring.)

    Raises:
        SSHConnectionError, SSHAuthenticationError: `peer` unreachable.
    """
    iface = _iface_name(hub)
    port_checks = " && ".join(
        f"ufw status | grep -qE '^{port}/tcp[[:space:]]+ALLOW'" for port in ports
    )
    check_cmd = (
        f"systemctl is-active wg-quick@{iface} 2>/dev/null | grep -qx active && "
        f"grep -q '^\\[Peer\\]' /etc/wireguard/{iface}.conf 2>/dev/null"
        + (f" && {port_checks}" if port_checks else "")
    )
    with SSHService(peer) as ssh:
        ssh.ensure_sudo(
            f"Checking wg-manage peer bootstrap status on {peer.ansible_host}"
        )
        return ssh.execute(f"sudo sh -c {shlex.quote(check_cmd)}").ok


def ensure_peer(
    hub: DeploymentHostConfig, peer: DeploymentHostConfig, ports: list[int]
) -> None:
    """Bootstrap `peer` as a WireGuard peer of `hub`, idempotently.

    `ports` is every port currently assigned to `peer` -- one bootstrap
    run opens firewall exceptions for all of them at once (see
    is_bootstrapped()'s docstring for why this must be the *complete*
    current set, not incremental).

    Early-returns if is_bootstrapped() is already True: no new peer on
    the hub, no key regeneration, no duplicate firewall rule. Otherwise:

    1. SSHes to `hub` and runs `wg-manage add <peer.inventory_hostname>`,
       capturing the printed client config. This must happen before the
       generated playbook's `wg-manage service add <peer>:<port>` call --
       resolve_target() resolves the peer name eagerly, at add-time, so
       the peer must already exist on the hub by then.
    2. Parses the hub's own WireGuard tunnel IP out of the captured
       config's `DNS = ` line -- the only place it's exposed to a peer;
       wg-manage's hub-side tunnel IP isn't a fixed convention (varies
       per hub deploy), so it can't be hardcoded or guessed.
    3. Runs the bundled wg_peer playbook against `peer` directly (an
       ad-hoc single-host inventory, mirroring
       CaddyProxy.ensure_installed()) to install WireGuard, write the
       config, bring up the tunnel, and open the scoped `ufw` rules.

    Raises:
        WgManageError: If the hub SSH round-trip fails, the peer is
            already registered on the hub despite not being bootstrapped
            (a prior partial failure, or a new service added to an
            already-bootstrapped peer -- both require manual
            reconciliation today, see the raised message), the hub's
            output couldn't be parsed, or the bootstrap playbook fails.
    """
    if is_bootstrapped(hub, peer, ports):
        return

    peer_name = peer.inventory_hostname
    result = ssh_exec(hub, f"wg-manage add {shlex.quote(peer_name)}")
    if not result.ok:
        detail = result.stderr.strip() or result.stdout.strip()
        if "already exists" in detail:
            # wg-manage add has no create-or-update semantics (unlike
            # `service add`) and can't reissue an already-issued peer's
            # private key. Two ways to land here: a previous run
            # registered the peer on the hub but failed before finishing
            # peer-side setup, OR the peer was already fully bootstrapped
            # for a different port set and a service was since added
            # (is_bootstrapped() requires *all* current ports to have a
            # rule, so a new port makes it False again even though the
            # peer/tunnel itself is fine). Auto-recovery isn't safely
            # possible in either case without reissuing keys; surface the
            # fix instead of a raw wg-manage error dump.
            raise WgManageError(
                f"wg-manage on {hub.ansible_host} already has a peer named "
                f"'{peer_name}', but it isn't fully bootstrapped for its "
                f"current ports ({', '.join(str(p) for p in ports)}). This "
                "is either a previous deploy that failed mid-bootstrap, or "
                "a new service added to an already-bootstrapped peer -- "
                "wg-manage can't reissue an existing peer's private key to "
                "recover automatically. SSH to the peer and check "
                f"`ufw status`/`wg show {_iface_name(hub)}` against what's "
                "expected; if the tunnel is fine and only a firewall rule "
                "is missing, add it by hand "
                f"(`ufw allow from <hub-wg-ip> to any port <port> proto "
                "tcp`); otherwise run `wg-manage rotate "
                f"{peer_name}` on the hub and re-provision the peer."
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

    playbook_path = _get_playbook_path()
    inventory_content = f"[all]\n{peer.to_ini_line()}\n"

    with (
        temp_secret_file(
            inventory_content, prefix="slipp-wgpeer-inv-", suffix=".ini"
        ) as inventory_path,
        # The captured config carries a WireGuard private key -- passed to
        # the playbook by file path (read via lookup('file', ...) on the
        # control node), never as a literal -e extra-var value, which
        # would land in the ansible-playbook argv and be visible to any
        # local user via `ps`.
        temp_secret_file(
            iface_config, prefix="slipp-wgpeer-conf-", suffix=".conf"
        ) as config_path,
    ):
        extra_vars = {
            "peer_config_path": str(config_path),
            "iface_name": _iface_name(hub),
            "hub_wg_ip": hub_wg_ip,
            "service_ports": ports,
        }

        log_dir = get_log_dir()
        run_result = run_playbook_with_spinner(
            str(playbook_path),
            str(inventory_path),
            label=f"Bootstrapping WireGuard peer {peer_name}",
            extra_vars=extra_vars,
            log_dir=log_dir,
        )

        if run_result.exit_code != 0:
            message = append_log_hint(
                f"WireGuard peer bootstrap failed for '{peer_name}' "
                f"(exit code {run_result.exit_code})",
                run_result,
            )
            raise WgManageError(message)
