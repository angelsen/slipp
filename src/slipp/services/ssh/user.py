"""User resolution service for SSH commands.

Extracts and consolidates user resolution logic from exec.py and ssh.py.
Provides a single source of truth for resolving which user to run commands as.
"""

from dataclasses import dataclass

from slipp.models.service import Runtime, Service
from slipp.services.ssh.client import SSHService


@dataclass
class UserResolution:
    """Result of user resolution with metadata.

    Attributes:
        user: Resolved username
        source: How the user was determined ("explicit", "detected", "default")
        warning: Optional warning message (e.g., detection failed)
    """

    user: str
    source: str
    warning: str | None = None


class UserResolver:
    """Resolve target user for SSH commands.

    This service handles the logic for determining which user to execute
    commands as, based on explicit flags, service detection, or defaults.
    """

    def __init__(self, ssh: SSHService):
        self.ssh = ssh

    def get_service_user(self, unit_name: str) -> str | None:
        """Detect user from systemd unit file.

        Tries two methods:
        1. Check User= directive in unit file
        2. Get MainPID and check actual process user

        Args:
            unit_name: Systemd unit name (e.g., 'nginx.service')

        Returns:
            Username (e.g., 'www-data', 'postgres') or None if not determinable
        """
        # Exit codes intentionally unchecked: detection is best-effort here;
        # any command failure or empty output falls through to None, and the
        # caller (resolve()) warns and falls back to default_user.
        try:
            result = self.ssh.execute(
                f"sudo systemctl show -p User --value {unit_name}"
            ).stdout.strip()

            if result:
                return result

            pid = self.ssh.execute(
                f"sudo systemctl show -p MainPID --value {unit_name}"
            ).stdout.strip()

            if pid and pid.isdigit() and pid != "0":
                user = self.ssh.execute(f"sudo stat -c '%U' /proc/{pid}").stdout.strip()
                if user and user != "root":
                    return user

            return None
        except Exception:
            return None

    def resolve(
        self,
        service: Service | None,
        explicit_user: str | None,
        default_user: str,
    ) -> UserResolution:
        """Resolve which user to run command as.

        Resolution order:
        1. Explicit --user flag wins
        2. Auto-detect from service (if provided)
           - Containers default to root
           - Systemd services: detect from unit file
        3. Fallback to default user (typically SSH user)

        Args:
            service: Service object (if service context specified)
            explicit_user: User from --user flag (if provided)
            default_user: Fallback user (typically SSH user)

        Returns:
            UserResolution with user, source, and optional warning
        """
        if explicit_user:
            return UserResolution(user=explicit_user, source="explicit")

        if service:
            if Runtime(service.runtime).is_container():
                return UserResolution(user="root", source="detected")

            detected = self.get_service_user(service.unit_name)
            if detected:
                return UserResolution(user=detected, source="detected")

            return UserResolution(
                user=default_user,
                source="default",
                warning=f"Could not detect user for '{service.name}', using {default_user}. "
                "Hint: Use -u <user> to specify explicitly",
            )

        return UserResolution(user=default_user, source="default")
