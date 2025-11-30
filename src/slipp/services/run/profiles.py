"""Run profile persistence and lifecycle management."""

from pathlib import Path

from slipp.models.run import RunProfile
from slipp.services.run.io import RunsConfigIO
from slipp.utils.errors import ProfileNotFoundError


class RunProfileService:
    """Manage run profile persistence and queries.

    Handles saving, loading, listing, and deleting run profiles from
    local project configuration.
    """

    def __init__(
        self, io: RunsConfigIO | None = None, project_root: Path | None = None
    ):
        self.io = io or RunsConfigIO()
        self.project_root = project_root or Path.cwd()

    def save_profile(self, name: str, profile: RunProfile) -> None:
        """Save or update a run profile."""
        profiles = self.io.load(self.project_root)
        profiles[name] = profile
        self.io.save(profiles, self.project_root)

    def get_profile(self, name: str) -> RunProfile:
        """Return a run profile by name.

        Raises:
            ProfileNotFoundError: If the profile does not exist.
        """
        profiles = self.io.load(self.project_root)
        if name not in profiles:
            raise ProfileNotFoundError(f"Profile '{name}' not found")
        return profiles[name]

    def list_profiles(self) -> dict[str, RunProfile]:
        """Return all saved run profiles."""
        return self.io.load(self.project_root)

    def delete_profile(self, name: str) -> None:
        """Delete a run profile.

        Raises:
            ProfileNotFoundError: If the profile does not exist.
        """
        profiles = self.io.load(self.project_root)
        if name not in profiles:
            raise ProfileNotFoundError(f"Profile '{name}' not found")
        del profiles[name]
        self.io.save(profiles, self.project_root)

    def profile_exists(self, name: str) -> bool:
        """Check whether a profile exists."""
        profiles = self.io.load(self.project_root)
        return name in profiles
