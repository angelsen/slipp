"""Caddy dev proxy service for routing production domains to local tunnels.

Manages Caddy installation (via bundled Ansible playbook) and dynamic route
management via Caddy's admin API.

Traffic flow:
  Internet → :443 (TLS) → iptables → :8443 (Caddy TLS)
                                          │
                          ┌───────────────┴───────────────┐
                          ↓                               ↓
                 dev domain match              fallback to Traefik
                 (TLS terminate)               (HTTPS proxy to :443)
                          ↓
                 localhost:{tunnel_port}
"""

import json
import logging
import re
import shlex
from importlib.resources import files
from pathlib import Path
from tempfile import NamedTemporaryFile

from slipp.models.host import AnsibleHost
from slipp.services.ansible import run_playbook
from slipp.services.ssh import SSHService
from slipp.utils.errors import CaddyProxyError

logger = logging.getLogger(__name__)


def _domain_to_route_id(domain: str) -> str:
    """Convert domain to Caddy route ID.

    Args:
        domain: Domain name (e.g., "app.example.com")

    Returns:
        Route ID (e.g., "dev-app-example-com")
    """
    safe_name = re.sub(r"[^a-zA-Z0-9-]", "-", domain.lower())
    return f"dev-{safe_name}"


def _push_route(host: AnsibleHost, route_config: dict, error_prefix: str) -> None:
    """Prepend a route to Caddy's config via the admin API.

    Args:
        host: Remote host running Caddy
        route_config: Caddy route object to prepend
        error_prefix: Message prefix used if the push fails

    Raises:
        CaddyProxyError: If the route push fails
    """
    route_json = json.dumps(route_config)
    jq_filter = shlex.quote(f"[{route_json}] + .")

    add_cmd = (
        f"curl -sf http://localhost:2019/config/apps/http/servers/srv1/routes | "
        f"jq {jq_filter} | "
        f"curl -sf -X PATCH 'http://localhost:2019/config/apps/http/servers/srv1/routes' "
        f"-H 'Content-Type: application/json' -d @-"
    )

    try:
        with SSHService(host) as ssh:
            result = ssh.execute(add_cmd)

            if not result.ok:
                detail = result.stderr.strip() or result.stdout.strip()
                raise CaddyProxyError(f"{error_prefix}: {detail}")

    except CaddyProxyError:
        raise
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
    ):
        """Initialize Caddy proxy for a host.

        Args:
            host: Target host for Caddy installation and routes
            acme_email: Email for Let's Encrypt certificate registration
            fallback_port: Port where existing service listens for HTTPS traffic
        """
        self.host = host
        self.acme_email = acme_email
        self.fallback_port = fallback_port
        self.route_ids: list[str] = []

    def __enter__(self) -> "CaddyProxy":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.cleanup()

    def is_port_443_free(self) -> bool:
        """Check if port 443 is available on the host.

        Returns:
            True if port 443 is free, False if bound

        Raises:
            SSHConnectionError: Host unreachable
            SSHAuthenticationError: SSH authentication failed
        """
        check_cmd = "ss -tln 2>/dev/null | grep -q ':443 '"

        with SSHService(self.host) as ssh:
            # grep -q exits 0 when the port is bound, 1 when free
            return not ssh.execute(check_cmd).ok

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
            "sudo iptables -t nat -S PREROUTING 2>/dev/null | grep -q 'slipp dev proxy' && "
            "curl -sf http://localhost:2019/config/ >/dev/null && "
            "curl -sf http://localhost:2020/check >/dev/null"
        )

        with SSHService(self.host) as ssh:
            return ssh.execute(f"bash -c '{check_cmd}'").ok

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

        with NamedTemporaryFile(
            mode="w",
            suffix=".ini",
            prefix="slipp-inventory-",
            delete=False,
        ) as f:
            inv_line = f"{self.host.inventory_hostname} ansible_host={self.host.ansible_host} ansible_user={self.host.ansible_user}"
            if self.host.ansible_port != 22:
                inv_line += f" ansible_port={self.host.ansible_port}"
            if self.host.key_file:
                inv_line += f" ansible_ssh_private_key_file={self.host.key_file}"

            f.write(f"[caddy_dev]\n{inv_line}\n")
            inventory_path = Path(f.name)

        try:
            extra_vars: dict[str, str] = {"fallback_port": str(self.fallback_port)}
            if self.acme_email:
                extra_vars["acme_email"] = self.acme_email

            result = run_playbook(
                str(playbook_path),
                str(inventory_path),
                extra_vars=extra_vars,
            )

            if result.exit_code != 0:
                raise CaddyProxyError(
                    f"Caddy installation failed (exit code {result.exit_code})\n"
                    "Check the ansible output above for details"
                )

            return False

        finally:
            inventory_path.unlink(missing_ok=True)

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
        route_id = f"proxy-{re.sub(r'[^a-zA-Z0-9-]', '-', f'{from_domain}{from_path}'.lower())}"

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
            self.host,
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

        handle: list[dict] = []
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
        _push_route(self.host, route_config, f"Failed to add route for {domain}")

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
            with SSHService(self.host) as ssh:
                result = ssh.execute(remove_cmd)
                if not result.ok:
                    logger.warning(
                        f"Failed to remove route {route_id}: {result.text.strip()}"
                    )
        except Exception as e:
            # Best-effort cleanup - log warning but don't fail
            logger.warning(f"Failed to remove route {route_id}: {e}")

    def cleanup(self) -> None:
        """Remove all routes added by this instance.

        Called automatically on exit to clean up dev routes.
        """
        for route_id in self.route_ids:
            self.remove_route(route_id)
        self.route_ids.clear()
