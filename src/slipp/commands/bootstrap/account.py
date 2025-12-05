"""Account command - create slipp service account on VPS."""

from pathlib import Path
from typing import Optional

import typer

from slipp import output
from slipp.models.host import AnsibleHost
from slipp.services.ssh import SSHService
from slipp.utils.errors import SSHConnectionError


def _create_user(ssh: SSHService, username: str, dry_run: bool) -> None:
    """Create slipp user account."""
    output.info("1. Creating user account...")

    if dry_run:
        output.hint(f"Would run: useradd -m -s /bin/bash {username}")
        return

    check_user = ssh.execute(f"id {username} 2>/dev/null || echo NOTFOUND")

    if "NOTFOUND" not in check_user:
        output.warning(f"User '{username}' already exists (skipping)")
        return

    ssh.execute(f"useradd -m -s /bin/bash {username}")

    verify = ssh.execute(f"id {username}")
    output.success(f"User created: {verify.strip()}")


def _copy_ssh_keys(
    ssh: SSHService, root_user: str, slipp_user: str, dry_run: bool
) -> None:
    """Copy SSH keys from root to slipp user."""
    output.info("2. Copying SSH keys...")

    if dry_run:
        output.hint(f"Would copy /root/.ssh to /home/{slipp_user}/.ssh")
        return

    check_ssh = ssh.execute("test -d /root/.ssh && echo EXISTS || echo NOTFOUND")

    if "NOTFOUND" in check_ssh:
        output.error("Root user has no .ssh directory")
        raise Exception("Root user must have SSH keys configured")

    ssh.execute(f"cp -r /root/.ssh /home/{slipp_user}/")

    ssh.execute(f"chown -R {slipp_user}:{slipp_user} /home/{slipp_user}/.ssh")

    # Set permissions (security critical)
    ssh.execute(f"chmod 700 /home/{slipp_user}/.ssh")
    ssh.execute(f"chmod 600 /home/{slipp_user}/.ssh/*")

    perms = ssh.execute(f"ls -ld /home/{slipp_user}/.ssh")
    output.success("SSH keys copied and secured")
    output.hint(f"  {perms.strip()}")


def _configure_sudoers(ssh: SSHService, username: str, dry_run: bool) -> None:
    """Configure sudoers for full sudo access (SSH-key gated)."""
    output.info("3. Configuring sudoers...")

    # Sudoers configuration (permissive - SSH key is the security gate)
    sudoers_content = f"""# slipp service account - full sudo access
# Authentication: SSH key (passphrase-protected)
# Authorization: User selects privilege via exec --user flag
# Default behavior: exec runs as slipp user (least privilege)
# Updated: 2025-11-18 for exec-user-control feature

{username} ALL=(ALL) NOPASSWD: ALL
"""

    if dry_run:
        output.hint(f"Would create /etc/sudoers.d/{username}:")
        output.hint(sudoers_content)
        return

    ssh.execute(
        f"""cat > /tmp/sudoers-{username} << 'SUDOERS_EOF'
{sudoers_content}
SUDOERS_EOF
"""
    )

    validation = ssh.execute(f"visudo -c -f /tmp/sudoers-{username}")

    if "parsed OK" not in validation:
        output.error("Sudoers syntax validation failed")
        output.hint(f"  {validation}")
        raise Exception("Sudoers file has syntax errors")

    # Move to sudoers.d (atomic operation)
    ssh.execute(f"mv /tmp/sudoers-{username} /etc/sudoers.d/{username}")
    ssh.execute(f"chmod 440 /etc/sudoers.d/{username}")

    output.success(f"Sudoers configured (/etc/sudoers.d/{username})")


def _verify_setup(host: str, port: int, username: str, ssh_key: Optional[Path]) -> None:
    """Verify slipp user can connect and run commands."""
    output.info("4. Verifying setup...")

    slipp_config = AnsibleHost(
        inventory_hostname="bootstrap-verify",
        ansible_host=host,
        ansible_user=username,
        ansible_port=port,
        key_file=ssh_key,
    )

    try:
        with SSHService(slipp_config) as ssh:
            whoami = ssh.execute("whoami").strip()
            output.success(f"SSH connection successful (user: {whoami})")

            systemctl = ssh.execute("sudo systemctl --version")
            version_line = systemctl.split("\n")[0]
            output.success(f"Sudo access verified ({version_line})")

            try:
                user_switch = ssh.execute("sudo -u root whoami").strip()
                output.success(f"User switching verified (sudo -u root: {user_switch})")
            except Exception as e:
                # Graceful degradation - warn but don't fail
                output.warning(f"User switching test failed: {e}")
                output.hint("  (This is expected with read-only sudoers)")

    except SSHConnectionError as e:
        output.error(f"Connection verification failed: {e}")
        raise Exception("Failed to connect as slipp user")

    except Exception as e:
        output.error(f"Verification failed: {e}")
        raise


def _display_completion(host: str, port: int, username: str) -> None:
    """Display success message and next steps."""
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
    ssh_key: Optional[Path] = typer.Option(
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

    # Create root SSH connection config
    root_config = AnsibleHost(
        inventory_hostname="bootstrap-root",  # Temporary host for bootstrap
        ansible_host=host,
        ansible_user=root_user,
        ansible_port=ssh_port,
        key_file=ssh_key,
    )

    try:
        with SSHService(root_config) as ssh:
            _create_user(ssh, slipp_user, dry_run)
            _copy_ssh_keys(ssh, root_user, slipp_user, dry_run)
            _configure_sudoers(ssh, slipp_user, dry_run)

            # Verify setup (not dry-run)
            if not dry_run:
                _verify_setup(host, ssh_port, slipp_user, ssh_key)

            _display_completion(host, ssh_port, slipp_user)

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

    except Exception as e:
        output.blank()
        output.error(f"Bootstrap failed: {e}")
        raise typer.Exit(1)
