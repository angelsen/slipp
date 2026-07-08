"""VPS service-account provisioning for slipp bootstrap."""

from pathlib import Path

from slipp import output
from slipp.models.host import AnsibleHost
from slipp.services.ssh import SSHService
from slipp.utils.errors import BootstrapError, SSHCommandError, SSHConnectionError


def _create_user(ssh: SSHService, username: str, dry_run: bool) -> None:
    """Create slipp user account.

    Args:
        ssh: SSH service connected to host.
        username: Username to create.
        dry_run: If True, show what would be done without making changes.
    """
    output.info("1. Creating user account...")

    if dry_run:
        output.hint(f"Would run: useradd -m -s /bin/bash {username}")
        return

    if ssh.execute(f"id {username}").ok:
        output.warning(f"User '{username}' already exists (skipping)")
        return

    ssh.execute(f"useradd -m -s /bin/bash {username}").check(
        f"Failed to create user '{username}'"
    )

    verify = ssh.execute(f"id {username}").check("Failed to verify created user")
    output.success(f"User created: {verify.stdout.strip()}")


def _copy_ssh_keys(
    ssh: SSHService, root_user: str, slipp_user: str, dry_run: bool
) -> None:
    """Copy SSH keys from root to slipp user.

    Args:
        ssh: SSH service connected to host.
        root_user: Root username.
        slipp_user: Slipp service account username.
        dry_run: If True, show what would be done without making changes.

    Raises:
        BootstrapError: If root has no SSH keys to copy.
    """
    output.info("2. Copying SSH keys...")

    if dry_run:
        output.hint(f"Would copy /root/.ssh to /home/{slipp_user}/.ssh")
        return

    if not ssh.execute("test -d /root/.ssh").ok:
        raise BootstrapError("Root user must have SSH keys configured")

    ssh.execute(f"cp -r /root/.ssh /home/{slipp_user}/").check(
        "Failed to copy SSH keys"
    )
    ssh.execute(f"chown -R {slipp_user}:{slipp_user} /home/{slipp_user}/.ssh").check(
        "Failed to chown SSH keys"
    )
    ssh.execute(f"chmod 700 /home/{slipp_user}/.ssh").check(
        "Failed to chmod SSH directory"
    )
    ssh.execute(f"chmod 600 /home/{slipp_user}/.ssh/*").check(
        "Failed to chmod SSH files"
    )

    perms = ssh.execute(f"ls -ld /home/{slipp_user}/.ssh").check(
        "Failed to verify SSH directory permissions"
    )
    output.success("SSH keys copied and secured")
    output.hint(f"  {perms.stdout.strip()}")


def _configure_sudoers(ssh: SSHService, username: str, dry_run: bool) -> None:
    """Configure sudoers for full sudo access (SSH-key gated).

    Args:
        ssh: SSH service connected to host.
        username: Slipp service account username.
        dry_run: If True, show what would be done without making changes.

    Raises:
        BootstrapError: If the generated sudoers file fails syntax validation.
    """
    output.info("3. Configuring sudoers...")

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
    ).check("Failed to write sudoers temp file")

    validation = ssh.execute(f"visudo -c -f /tmp/sudoers-{username}")
    if not validation.ok:
        raise BootstrapError(f"Sudoers file has syntax errors\n  {validation.text}")

    ssh.execute(f"mv /tmp/sudoers-{username} /etc/sudoers.d/{username}").check(
        "Failed to install sudoers file"
    )
    ssh.execute(f"chmod 440 /etc/sudoers.d/{username}").check(
        "Failed to chmod sudoers file"
    )

    output.success(f"Sudoers configured (/etc/sudoers.d/{username})")


def _verify_setup(host: str, port: int, username: str, ssh_key: Path | None) -> None:
    """Verify slipp user can connect and run commands.

    Args:
        host: Hostname or IP address.
        port: SSH port.
        username: Slipp service account username.
        ssh_key: Path to SSH private key.

    Raises:
        BootstrapError: If connection or command execution fails.
    """
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
            whoami = ssh.execute("whoami").check("whoami failed").stdout.strip()
            output.success(f"SSH connection successful (user: {whoami})")

            systemctl = ssh.execute("sudo systemctl --version").check(
                "sudo systemctl --version failed"
            )
            version_line = systemctl.stdout.split("\n")[0]
            output.success(f"Sudo access verified ({version_line})")

            user_switch = ssh.execute("sudo -u root whoami")
            if user_switch.ok:
                output.success(
                    f"User switching verified (sudo -u root: {user_switch.stdout.strip()})"
                )
            else:
                output.warning(
                    f"User switching test failed: {user_switch.text.strip()}"
                )
                output.hint("  (This is expected with read-only sudoers)")

    except SSHConnectionError as e:
        raise BootstrapError(f"Failed to connect as slipp user: {e}") from e
    except SSHCommandError as e:
        raise BootstrapError(f"Setup verification command failed: {e}") from e


def provision_account(
    host: str,
    root_user: str,
    ssh_key: Path | None,
    ssh_port: int,
    slipp_user: str,
    dry_run: bool,
) -> None:
    """Provision a slipp service account on a VPS via a root SSH connection.

    Creates the service account, copies root's SSH keys, configures
    passwordless sudo, then (unless dry_run) verifies the new account works.

    Args:
        host: Hostname or IP address.
        root_user: Root username for the initial connection.
        ssh_key: SSH private key for the root connection.
        ssh_port: SSH port.
        slipp_user: Name of the service account to create.
        dry_run: If True, show what would be done without making changes.

    Raises:
        SSHConnectionError: If the initial root SSH connection fails.
        BootstrapError: If a provisioning step fails.
    """
    root_config = AnsibleHost(
        inventory_hostname="bootstrap-root",  # Temporary host for bootstrap
        ansible_host=host,
        ansible_user=root_user,
        ansible_port=ssh_port,
        key_file=ssh_key,
    )

    with SSHService(root_config) as ssh:
        _create_user(ssh, slipp_user, dry_run)
        _copy_ssh_keys(ssh, root_user, slipp_user, dry_run)
        _configure_sudoers(ssh, slipp_user, dry_run)

        if not dry_run:
            _verify_setup(host, ssh_port, slipp_user, ssh_key)
