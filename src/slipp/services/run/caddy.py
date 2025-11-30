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

    def is_port_443_free(self) -> bool:
        """Check if port 443 is available on the host.

        Returns:
            True if port 443 is free, False if bound
        """
        check_cmd = "ss -tln 2>/dev/null | grep -q ':443 ' && echo bound || echo free"

        try:
            with SSHService(self.host) as ssh:
                result = ssh.execute(check_cmd).strip()
                return result == "free"
        except Exception:
            # Assume free if check fails (install will fail later with better error)
            return True

    def is_installed(self) -> bool:
        """Check if Caddy dev proxy is installed and healthy.

        Checks:
        1. Caddy service is exactly "active" (not reloading/failed)
        2. iptables PREROUTING rule exists
        3. Admin API responds
        4. Permission endpoint responds (on-demand TLS configured)

        Returns:
            True if installed and healthy
        """
        check_cmd = (
            "systemctl is-active caddy 2>/dev/null | grep -qx active && "
            "sudo iptables -t nat -S PREROUTING 2>/dev/null | grep -q 'slipp dev proxy' && "
            "curl -sf http://localhost:2019/config/ >/dev/null && "
            "curl -sf http://localhost:2020/check >/dev/null"
        )

        try:
            with SSHService(self.host) as ssh:
                result = ssh.execute(f"bash -c '{check_cmd}' && echo OK")
                return "OK" in result
        except Exception:
            return False

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

    def add_route(self, domain: str, local_port: int) -> str:
        """Add a dev route to Caddy.

        Routes traffic for the domain to localhost:{local_port} where
        the SSH tunnel is listening.

        Args:
            domain: Domain to route (e.g., "app.example.com")
            local_port: Local port on server (SSH tunnel endpoint)

        Returns:
            Route ID for later removal

        Raises:
            CaddyProxyError: If route addition fails
        """
        route_id = _domain_to_route_id(domain)

        route_config = {
            "@id": route_id,
            "match": [{"host": [domain]}],
            "handle": [
                {
                    "handler": "reverse_proxy",
                    "upstreams": [{"dial": f"localhost:{local_port}"}],
                }
            ],
            "terminal": True,
        }

        # Must prepend to routes array so dev routes match before fallback
        # (Caddy JSON routes are evaluated sequentially, first match wins)
        route_json = json.dumps(route_config)

        add_cmd = (
            f"curl -sf http://localhost:2019/config/apps/http/servers/srv1/routes | "
            f"jq '[{route_json}] + .' | "
            f"curl -sf -X PATCH 'http://localhost:2019/config/apps/http/servers/srv1/routes' "
            f"-H 'Content-Type: application/json' -d @-"
        )

        try:
            with SSHService(self.host) as ssh:
                result = ssh.execute(add_cmd)

                if result and "error" in result.lower():
                    raise CaddyProxyError(f"Failed to add route: {result}")

        except CaddyProxyError:
            raise
        except Exception as e:
            raise CaddyProxyError(f"Failed to add route for {domain}: {e}") from e

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
                ssh.execute(remove_cmd)
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
