"""Interactive prompt utilities for launch command."""

import socket

import typer

from slipp import output
from slipp.constants import DEFAULT_ENV, DEFAULT_SSH_PORT, DEFAULT_SSH_USER
from slipp.models.deployment import DeploymentHostConfig, InventoryConfig
from slipp.models.host import AnsibleHost
from slipp.models.service import Runtime
from slipp.services.ssh import SSHService
from slipp.utils.errors import SSHAuthenticationError, SSHConnectionError
from slipp.utils.network import is_ip_address


def _test_ssh_connectivity(host: str, user: str, port: int) -> bool:
    """Test SSH connectivity to target host.

    Attempts to establish an SSH connection to verify the host is reachable
    and authentication will work before generating deployment files.

    Args:
        host: Target hostname or IP
        user: SSH username
        port: SSH port

    Returns:
        True if connection succeeds, False otherwise

    Example:
        >>> if _test_ssh_connectivity("46.251.249.252", "root", 22):
        ...     print("Connection successful!")
    """
    try:
        host_config = AnsibleHost(
            inventory_hostname="connectivity-test",
            ansible_host=host,
            ansible_user=user,
            ansible_port=port,
        )

        with SSHService(host_config):
            pass

        return True

    except SSHAuthenticationError as e:
        output.warning(f"SSH authentication failed: {e}")
        output.hint(f"Ensure SSH key is configured: ssh-copy-id {user}@{host}")
        return False

    except SSHConnectionError as e:
        output.warning(f"SSH connection failed: {e}")
        output.hint("Ensure SSH is enabled and host is reachable")
        return False

    except socket.gaierror as e:
        output.warning(f"DNS resolution failed: {e}")
        output.hint("Check hostname is correct and DNS is working")
        return False

    except Exception as e:
        output.warning(f"Unexpected error: {e}")
        return False


def get_inventory_config(environment: str = DEFAULT_ENV) -> InventoryConfig:
    """Get inventory configuration via interactive prompts.

    Prompts for:
    - Target host (IP or domain)
    - SSH user (default: root)
    - SSH port (default: 22)
    - App domain (for Caddy)

    Tests SSH connectivity before returning.

    Args:
        environment: Environment name (production, dev, staging, etc.)

    Returns:
        InventoryConfig with specified environment host populated

    Raises:
        typer.Exit: User aborted or SSH test failed

    Example:
        >>> config = get_inventory_config("production")
        >>> print(config.hosts["production"].ansible_host)
        46.251.249.252
    """
    output.task("Inventory Configuration")
    output.info("Configure deployment target")
    output.blank()

    ansible_host = output.prompt("Target host (IP or domain)")
    ansible_user = output.prompt("SSH user", default=DEFAULT_SSH_USER)
    ansible_port = output.prompt("SSH port", default=DEFAULT_SSH_PORT, type=int)
    app_domain = output.prompt("App domain")
    if is_ip_address(app_domain):
        admin_email = None
    else:
        admin_email = output.prompt(
            "Admin email (for HTTPS certificates)",
            default=f"admin@{app_domain}" if "@" not in app_domain else "",
        )

    output.blank()
    output.info("Runtime")
    output.hint("Choose how the app runs on the server:")
    output.hint("  podman  - Container, rootless, no daemon")
    output.hint("  docker  - Container, broader compatibility")
    output.hint("  systemd - Native process, no container runtime needed")
    output.blank()

    valid_runtimes = [r.value for r in Runtime]
    while True:
        runtime = output.prompt("Runtime", default=Runtime.DOCKER.value)
        if runtime in valid_runtimes:
            break
        output.warning(
            f"Invalid runtime '{runtime}'. Choose one of: {', '.join(valid_runtimes)}"
        )

    try:
        host_config = DeploymentHostConfig(
            inventory_hostname=environment,
            ansible_host=ansible_host,
            ansible_user=ansible_user,
            ansible_port=ansible_port,
            app_domain=app_domain,
            admin_email=admin_email,
            runtime=Runtime(runtime),
        )
    except Exception as e:
        output.error(f"Invalid configuration: {e}")
        raise typer.Exit(1)

    output.info("Testing SSH connectivity...")

    if not _test_ssh_connectivity(ansible_host, ansible_user, ansible_port):
        retry = output.confirm("Connection failed. Continue anyway?", default=False)
        if not retry:
            output.error("SSH connectivity test failed - aborting")
            raise typer.Exit(1)
    else:
        output.success("SSH connection successful")

    inventory = InventoryConfig(hosts={environment: host_config})
    return inventory
