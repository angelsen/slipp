"""Account command - create slipp service account on VPS."""

from pathlib import Path

import typer

from slipp import output
from slipp.services.bootstrap import provision_account
from slipp.utils.errors import BootstrapError, SSHConnectionError


def _display_completion(host: str, port: int, username: str) -> None:
    """Display success message and next steps.

    Args:
        host: Hostname or IP address.
        port: SSH port.
        username: Slipp service account username.
    """
    output.blank()
    output.success("Bootstrap complete!")
    output.blank()

    output.info("Next steps:")
    output.list_items(
        [
            f"Configure your inventory.yml:\n   ansible_host: {host}\n   ansible_user: {username}\n   ansible_port: {port}",
            'Test slipp commands:\n   slipp ps\n   slipp exec "whoami"',
        ],
        numbered=True,
    )
    output.blank()
    output.warning("Security note:")
    output.list_items(
        [
            "Ensure your SSH key is passphrase-protected",
            "ssh-keygen -p -f ~/.ssh/id_ed25519",
        ]
    )
    output.blank()


def account_command(
    host: str = typer.Argument(..., help="VPS hostname or IP address"),
    root_user: str = typer.Option(
        "root", "--root-user", help="Root user for initial connection (default: root)"
    ),
    ssh_key: Path | None = typer.Option(
        None,
        "--ssh-key",
        help="SSH private key for root connection (default: auto-discover)",
    ),
    ssh_port: int = typer.Option(22, "--port", "-p", help="SSH port (default: 22)"),
    slipp_user: str = typer.Option(
        "slipp", "--user", help="Name of service account to create (default: slipp)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without making changes"
    ),
) -> None:
    """Create slipp service account on VPS."""
    output.blank()
    output.info(f"Bootstrapping slipp on {host}")
    output.hint(f"Connecting as {root_user}...")
    output.blank()

    try:
        provision_account(host, root_user, ssh_key, ssh_port, slipp_user, dry_run)
    except SSHConnectionError as e:
        output.blank()
        output.error(f"SSH connection failed: {e}")
        output.warning("Troubleshooting:")
        output.list_items(
            [
                f"Verify SSH access: ssh {root_user}@{host}",
                "Check host is in ~/.ssh/known_hosts",
                f"Verify SSH key: {ssh_key or 'auto-discover'}",
            ]
        )
        raise typer.Exit(1)
    except BootstrapError as e:
        output.blank()
        output.error(f"Bootstrap failed: {e}")
        raise typer.Exit(1)

    _display_completion(host, ssh_port, slipp_user)
