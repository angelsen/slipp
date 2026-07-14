"""Caddy dev proxy service for routing production domains to local tunnels.

Manages Caddy installation (via bundled Ansible playbook) and dynamic route
management via Caddy's admin API.

Traffic flow:
  Internet → :443 (TLS) → iptables → :8443 (Caddy TLS)
                                          │
                          ┌───────────────┴───────────────┐
                          ↓                               ↓
                 dev domain match              fallback to Traefik
                 (TLS terminate)          (HTTPS proxy to :{fallback_port})
                          ↓
                 localhost:{tunnel_port}
"""

import json
import re
import shlex
from contextlib import ExitStack
from importlib.resources import files
from pathlib import Path
from typing import Any

from slipp import output
from slipp.models.host import AnsibleHost
from slipp.services.ansible import (
    maybe_become_password_file,
    run_playbook,
    spinner_progress_callback,
)
from slipp.services.ssh import SSHService
from slipp.utils.errors import CaddyProxyError, SSHCommandError
from slipp.utils.files import get_log_dir, temp_secret_file


def _slugify(text: str) -> str:
    """Sanitize text into a Caddy @id-safe slug."""
    return re.sub(r"[^a-zA-Z0-9-]", "-", text.lower())


def _domain_to_route_id(domain: str) -> str:
    """Convert domain to Caddy route ID.

    Args:
        domain: Domain name (e.g., "app.example.com")

    Returns:
        Route ID (e.g., "dev-app-example-com")
    """
    return f"dev-{_slugify(domain)}"


def _push_route(
    ssh: SSHService, route_config: dict[str, Any], error_prefix: str
) -> None:
    """Prepend a route to Caddy's config via the admin API, idempotently.

    Caddy rejects a config containing two routes with the same "@id", so
    re-pushing a route (e.g. re-running `run --tunnel-out` for a domain
    that's already routed) must replace the existing entry rather than
    duplicate it: any existing route sharing this route's "@id" is
    filtered out of the current list before the new one is prepended.

    Note:
        The GET -> filter -> PATCH sequence below is not atomic. Two
        concurrent slipp sessions targeting the same host could race and
        drop each other's routes. Acceptable for a single-developer tool;
        if concurrent sessions become a real need, switch to an atomic
        DELETE by "@id" (as cleanup already does) followed by a POST that
        appends to the routes array.

        route_config is piped in via stdin rather than embedded in the
        command string - it may contain an HTTP basic auth password hash
        (see add_route's `auth` param), and every SSH command is logged
        verbatim to .slipp/logs/ (see _prepare_sudo_command for the same
        stdin-piping pattern used for sudo passwords).

    Args:
        ssh: Open SSH connection to the host running Caddy
        route_config: Caddy route object to prepend. Must include "@id".
        error_prefix: Message prefix used if the push fails

    Raises:
        CaddyProxyError: If the route push fails
    """
    route_json = json.dumps(route_config)
    route_id_json = json.dumps(route_config["@id"])
    jq_program = shlex.quote(
        f'[$newroute] + (map(select(.["@id"] != {route_id_json})))'
    )

    add_cmd = (
        "route_json=$(cat) && "
        "curl -sf http://localhost:2019/config/apps/http/servers/srv1/routes | "
        f'jq --argjson newroute "$route_json" {jq_program} | '
        "curl -sf -X PATCH 'http://localhost:2019/config/apps/http/servers/srv1/routes' "
        "-H 'Content-Type: application/json' -d @-"
    )

    try:
        ssh.execute(add_cmd, stdin_data=route_json).check(error_prefix)
    except SSHCommandError as e:
        raise CaddyProxyError(str(e)) from e
    except Exception as e:
        raise CaddyProxyError(f"{error_prefix}: {e}") from e


def _get_playbook_path() -> Path:
    """Get path to bundled caddy-dev playbook.

    Returns:
        Path to playbook.yml

    Raises:
        CaddyProxyError: If playbook not found
    """
    try:
        playbook_dir = files("slipp.playbooks.caddy_dev")
        playbook_path = Path(str(playbook_dir.joinpath("playbook.yml")))

        if not playbook_path.exists():
            raise CaddyProxyError(f"Playbook not found: {playbook_path}")

        return playbook_path

    except CaddyProxyError:
        raise
    except Exception as e:
        raise CaddyProxyError(f"Failed to locate bundled playbook: {e}") from e


class CaddyProxy:
    """Manages Caddy dev proxy installation and routes.

    Provides lazy installation via bundled Ansible playbook and dynamic
    route management via Caddy's admin API.

    Example:
        >>> host = AnsibleHost(ansible_host="server.example.com", ansible_user="root")
        >>> proxy = CaddyProxy(host, acme_email="admin@example.com")
        >>> proxy.ensure_installed()
        >>> route_id = proxy.add_route("app.example.com", 5173)
        >>> # ... dev session ...
        >>> proxy.cleanup()
    """

    def __init__(
        self,
        host: AnsibleHost,
        acme_email: str | None = None,
        fallback_port: int = 9443,
        ask_become_pass: bool = False,
    ):
        """Initialize Caddy proxy for a host.

        Args:
            host: Target host for Caddy installation and routes
            acme_email: Email for Let's Encrypt certificate registration
            fallback_port: Port where existing service listens for HTTPS traffic
            ask_become_pass: Prompt for the sudo/become password before
                installing (target host has no passwordless sudo).
        """
        self.host = host
        self.acme_email = acme_email
        self.fallback_port = fallback_port
        self.ask_become_pass = ask_become_pass
        self.route_ids: list[str] = []
        self._ssh: SSHService | None = None

    def __enter__(self) -> "CaddyProxy":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.cleanup()

    def _connection(self) -> SSHService:
        """One SSH connection to this host, reused across all Caddy API calls.

        A CaddyProxy instance is reused for every route added/removed on a
        given host during a single `slipp run` -- opening a fresh SSH
        connection per call would mean one handshake per route instead of
        one per host.
        """
        if self._ssh is None:
            ssh = SSHService(self.host)
            ssh.connect()
            self._ssh = ssh
        return self._ssh

    def is_port_443_free(self) -> bool:
        """Check if port 443 is available on the host.

        Returns:
            True if port 443 is free, False if bound

        Raises:
            SSHConnectionError: Host unreachable
            SSHAuthenticationError: SSH authentication failed
        """
        check_cmd = "ss -tln 2>/dev/null | grep -q ':443 '"

        # grep -q exits 0 when the port is bound, 1 when free
        return not self._connection().execute(check_cmd).ok

    def is_installed(self) -> bool:
        """Check if Caddy dev proxy is installed and healthy.

        Checks:
        1. Caddy service is exactly "active" (not reloading/failed)
        2. iptables PREROUTING rule exists
        3. Admin API responds
        4. Permission endpoint responds (on-demand TLS configured)

        Returns:
            True if installed and healthy

        Raises:
            SSHConnectionError: Host unreachable
            SSHAuthenticationError: SSH authentication failed
        """
        check_cmd = (
            "systemctl is-active caddy 2>/dev/null | grep -qx active && "
            "iptables -t nat -S PREROUTING 2>/dev/null | grep -q slipp && "
            "curl -sf http://localhost:2019/config/ >/dev/null && "
            "curl -sf http://localhost:2020/check >/dev/null"
        )

        # Wrapped in a single leading `sudo sh -c` (rather than `bash -c
        # '... sudo iptables ...'`) so _prepare_sudo_command's password
        # piping actually applies -- see its docstring. The iptables grep
        # pattern must not itself contain a single quote: nesting one
        # inside this outer '...' would split the string into extra
        # positional args to `sh -c`, silently dropping everything after
        # it from the executed script (the two curl checks never ran).
        connection = self._connection()
        connection.ensure_sudo("Checking dev proxy status")
        return connection.execute(f"sudo sh -c '{check_cmd}'").ok

    def ensure_installed(self) -> bool:
        """Install Caddy dev proxy if not already installed.

        Uses bundled Ansible playbook to:
        1. Install Caddy from apt
        2. Configure iptables PREROUTING :443 → :8443
        3. Deploy Caddyfile with admin API + fallback
        4. Start/enable Caddy service

        Returns:
            True if already installed, False if installation was performed

        Raises:
            CaddyProxyError: If installation fails
        """
        if self.is_installed():
            return True

        playbook_path = _get_playbook_path()
        inventory_content = f"[caddy_dev]\n{self.host.to_ini_line()}\n"

        with temp_secret_file(
            inventory_content, prefix="slipp-inventory-", suffix=".ini"
        ) as inventory_path:
            extra_vars: dict[str, str] = {"fallback_port": str(self.fallback_port)}
            if self.acme_email:
                extra_vars["acme_email"] = self.acme_email

            log_dir = get_log_dir()
            with ExitStack() as stack:
                become_pw_file = maybe_become_password_file(stack, self.ask_become_pass)
                with output.spinner("Installing Caddy dev proxy") as update:
                    result = run_playbook(
                        str(playbook_path),
                        str(inventory_path),
                        extra_vars=extra_vars,
                        become_pw_file=become_pw_file,
                        log_dir=log_dir,
                        on_progress=spinner_progress_callback(update),
                    )

            if result.exit_code != 0:
                hint = (
                    ""
                    if self.ask_become_pass
                    else "\nHint: retry with --ask-become-pass if the target host has no passwordless sudo"
                )
                message = f"Caddy installation failed (exit code {result.exit_code})"
                if result.log_path:
                    message += f"\nSee log: {result.log_path}"
                raise CaddyProxyError(message + hint)

            return False

    def add_proxy_route(
        self, from_domain: str, from_path: str, to_host: str, to_path: str
    ) -> str:
        """Add a path-based proxy route to Caddy.

        Routes traffic matching domain + path to a different host + path,
        rewriting the URI in the process.

        Args:
            from_domain: Source domain to match (e.g., "matrix.example.com")
            from_path: Source path to match (e.g., "/_matrix/client/v3/keys/upload")
            to_host: Target host:port (e.g., "localhost:5173")
            to_path: Target path (e.g., "/api/matrix/keys/upload")

        Returns:
            Route ID for later removal

        Raises:
            CaddyProxyError: If route addition fails
        """
        route_id = f"proxy-{_slugify(f'{from_domain}{from_path}')}"

        route_config = {
            "@id": route_id,
            "match": [{"host": [from_domain], "path": [from_path]}],
            "handle": [
                {
                    "handler": "subroute",
                    "routes": [
                        {"handle": [{"handler": "rewrite", "uri": to_path}]},
                        {
                            "handle": [
                                {
                                    "handler": "reverse_proxy",
                                    "upstreams": [{"dial": to_host}],
                                }
                            ]
                        },
                    ],
                }
            ],
            "terminal": True,
        }

        _push_route(
            self._connection(),
            route_config,
            f"Failed to add proxy route for {from_domain}{from_path}",
        )

        self.route_ids.append(route_id)
        return route_id

    def add_route(
        self,
        domain: str,
        local_port: int,
        auth: tuple[str, str] | None = None,
    ) -> str:
        """Add a dev route to Caddy.

        Routes traffic for the domain to localhost:{local_port} where
        the SSH tunnel is listening.

        Args:
            domain: Domain to route (e.g., "app.example.com")
            local_port: Local port on server (SSH tunnel endpoint)
            auth: Optional (username, bcrypt-hash) for HTTP basic auth

        Returns:
            Route ID for later removal

        Raises:
            CaddyProxyError: If route addition fails
        """
        route_id = _domain_to_route_id(domain)

        handle: list[dict[str, Any]] = []
        if auth:
            username, password_hash = auth
            handle.append(
                {
                    "handler": "authentication",
                    "providers": {
                        "http_basic": {
                            "accounts": [
                                {"username": username, "password": password_hash}
                            ]
                        }
                    },
                }
            )
        handle.append(
            {
                "handler": "reverse_proxy",
                "upstreams": [{"dial": f"localhost:{local_port}"}],
            }
        )

        route_config = {
            "@id": route_id,
            "match": [{"host": [domain]}],
            "handle": handle,
            "terminal": True,
        }

        # Prepend to routes so dev routes match before fallback (first match wins)
        _push_route(
            self._connection(), route_config, f"Failed to add route for {domain}"
        )

        self.route_ids.append(route_id)
        return route_id

    def remove_route(self, route_id: str) -> None:
        """Remove a dev route from Caddy.

        Args:
            route_id: Route ID returned from add_route()

        Note:
            Failures are logged but not raised (best-effort cleanup)
        """
        remove_cmd = f"curl -sf -X DELETE 'http://localhost:2019/id/{route_id}'"

        try:
            result = self._connection().execute(remove_cmd)
            if not result.ok:
                output.warning(
                    f"Failed to remove route {route_id}: {result.text.strip()}"
                )
        except Exception as e:
            # Best-effort cleanup - warn but don't fail
            output.warning(f"Failed to remove route {route_id}: {e}")

    def cleanup(self) -> None:
        """Remove all routes added by this instance and close the connection.

        Called automatically on exit to clean up dev routes.
        """
        for route_id in self.route_ids:
            self.remove_route(route_id)
        self.route_ids.clear()

        if self._ssh is not None:
            self._ssh.close()
            self._ssh = None
