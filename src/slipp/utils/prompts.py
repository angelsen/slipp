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


def test_ssh_connectivity(host: str, user: str, port: int) -> bool:
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
        >>> if test_ssh_connectivity("46.251.249.252", "root", 22):
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
        print("Ensure SSH key is configured: ssh-copy-id {user}@{host}")
        return False

    except SSHConnectionError as e:
        output.warning(f"SSH connection failed: {e}")
        print("Ensure SSH is enabled and host is reachable")
        return False

    except socket.gaierror as e:
        output.warning(f"DNS resolution failed: {e}")
        print("Check hostname is correct and DNS is working")
        return False

    except Exception as e:
        output.warning(f"Unexpected error: {e}")
        return False


def get_inventory_config(
    environment: str = DEFAULT_ENV, reconfigure: bool = False
) -> InventoryConfig:
    """Get inventory configuration via interactive prompts.

    Prompts for:
    - Target host (IP or domain)
    - SSH user (default: root)
    - SSH port (default: 22)
    - App domain (for Caddy)

    Tests SSH connectivity before returning.

    Args:
        environment: Environment name (production, dev, staging, etc.)
        reconfigure: If True, skip loading existing configuration

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
    print("Configure deployment target\n")

    ansible_host = typer.prompt("Target host (IP or domain)")
    ansible_user = typer.prompt("SSH user", default=DEFAULT_SSH_USER)
    ansible_port = typer.prompt("SSH port", default=DEFAULT_SSH_PORT, type=int)
    app_domain = typer.prompt("App domain")
    admin_email = typer.prompt(
        "Admin email (for HTTPS certificates)",
        default=f"admin@{app_domain}" if "@" not in app_domain else "",
    )

    print("\nRuntime")
    print("Choose how the app runs on the server:")
    print("  docker  - Container, recommended, broader compatibility")
    print("  podman  - Container, rootless, no daemon")
    print("  systemd - Native process, no container runtime needed\n")

    valid_runtimes = [r.value for r in Runtime]
    while True:
        runtime = typer.prompt("Runtime", default=Runtime.DOCKER.value)
        if runtime in valid_runtimes:
            break
        output.warning(
            f"Invalid runtime '{runtime}'. Choose one of: {', '.join(valid_runtimes)}"
        )

    try:
        host_config = DeploymentHostConfig(
            name=environment,
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

    if not test_ssh_connectivity(ansible_host, ansible_user, ansible_port):
        retry = typer.confirm("Connection failed. Continue anyway?", default=False)
        if not retry:
            output.error("SSH connectivity test failed - aborting")
            raise typer.Exit(1)
    else:
        output.success("✓ SSH connection successful\n")

    inventory = InventoryConfig(hosts={environment: host_config})
    return inventory
