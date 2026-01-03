"""Runs config IO - pure file operations for .slipp/runs.yaml.

Low-level IO layer for run profiles. Use RunProfileService for semantic operations.
"""

from pathlib import Path

import yaml

from slipp.models.run import ProxyRoute, RunProfile, TunnelConfig


RUNS_FILENAME = ".slipp/runs.yaml"


class RunsConfigIO:
    """Pure IO operations for .slipp/runs.yaml files."""

    @staticmethod
    def get_path(project_root: Path | None = None) -> Path:
        """Get path to .slipp/runs.yaml.

        Args:
            project_root: Project root directory. Defaults to current directory.

        Returns:
            Path to runs configuration file.
        """
        root = project_root or Path.cwd()
        return root / RUNS_FILENAME

    @staticmethod
    def load(project_root: Path | None = None) -> dict[str, RunProfile]:
        """Load run profiles from .slipp/runs.yaml.

        Returns empty dict if file doesn't exist. Silently ignores parse errors.

        Args:
            project_root: Project root directory. Defaults to current directory.

        Returns:
            Dictionary mapping profile names to RunProfile objects.
        """
        path = RunsConfigIO.get_path(project_root)

        if not path.exists():
            return {}

        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}

            profiles = {}
            for name, profile_data in data.items():
                tunnels = None
                if profile_data.get("tunnels"):
                    tunnel_data = profile_data["tunnels"]
                    tunnels = TunnelConfig.model_validate(
                        {
                            "out": tunnel_data.get("out", []),
                            "in": tunnel_data.get("in", []),
                        }
                    )

                proxy_routes = [
                    ProxyRoute.model_validate(r)
                    for r in profile_data.get("proxy", [])
                ]

                profiles[name] = RunProfile(
                    cmd=profile_data["cmd"],
                    vaults=profile_data.get("vaults", []),
                    env=profile_data.get("env", []),
                    tunnels=tunnels,
                    proxy=proxy_routes,
                    acme_email=profile_data.get("acme_email"),
                )

            return profiles

        except Exception:
            return {}

    @staticmethod
    def save(profiles: dict[str, RunProfile], project_root: Path | None = None) -> Path:
        """Save run profiles to .slipp/runs.yaml.

        Args:
            profiles: Dictionary mapping profile names to RunProfile objects.
            project_root: Project root directory. Defaults to current directory.

        Returns:
            Path to saved configuration file.
        """
        path = RunsConfigIO.get_path(project_root)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {}
        for name, profile in profiles.items():
            profile_data: dict = {"cmd": profile.cmd}

            if profile.vaults:
                profile_data["vaults"] = profile.vaults

            if profile.env:
                profile_data["env"] = profile.env

            if profile.tunnels:
                tunnels_data: dict = {}
                if profile.tunnels.out:
                    tunnels_data["out"] = profile.tunnels.out
                if profile.tunnels.in_:
                    tunnels_data["in"] = profile.tunnels.in_
                if tunnels_data:
                    profile_data["tunnels"] = tunnels_data

            if profile.proxy:
                profile_data["proxy"] = [
                    {"from": r.from_, "to": r.to, "host": r.host}
                    for r in profile.proxy
                ]

            if profile.acme_email:
                profile_data["acme_email"] = profile.acme_email

            data[name] = profile_data

        with open(path, "w") as f:
            f.write("# Run profiles for slipp run\n")
            f.write("# Edit manually or use 'slipp run <name> --cmd \"...\"'\n\n")
            if data:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        return path
