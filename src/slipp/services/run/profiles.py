"""Run profile persistence, inheritance, and lifecycle management.

Profiles are stored in slipp.yaml under `runs:` (git-tracked), with
personal overrides in `.slipp/runs.local.yaml` (untracked, not created
automatically).
"""

import shlex
from pathlib import Path
from typing import Any

import bcrypt
import yaml
from pydantic import ValidationError

from slipp import output
from slipp.models.local_config import LocalConfig
from slipp.models.run import ProxyRoute, RunProfile, TunnelConfig
from slipp.services.config.local import LocalConfigService
from slipp.services.ssh import (
    parse_container_tunnel_in,
    parse_tunnel_in,
    parse_tunnel_out,
)
from slipp.utils.config_store import backup_corrupt_file
from slipp.utils.errors import ConfigError, ProfileNotFoundError, ProxyRouteError

LOCAL_RUNS_FILENAME = ".slipp/runs.local.yaml"


def _load_raw_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file as a raw dict, tolerating a missing, invalid, or malformed file."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        backup_corrupt_file(path, str(path), e)
        return {}

    if not isinstance(data, dict):
        output.warning(f"Ignoring invalid {path}: expected a mapping of profile names")
        return {}
    return data


class RunProfileService:
    """Manage run profile persistence, inheritance, and queries."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or LocalConfigService.resolve_root()
        self._raw_cache: dict[str, dict[str, Any]] | None = None

    def _local_path(self) -> Path:
        return self.project_root / LOCAL_RUNS_FILENAME

    def _raw_profiles(self) -> dict[str, dict[str, Any]]:
        """Union of all profile sources: local overrides tracked.

        Cached per instance so a single command invocation (which typically
        checks existence then fetches) only reads disk and warns once.
        """
        if self._raw_cache is not None:
            return self._raw_cache

        raw: dict[str, dict[str, Any]] = {}

        config = LocalConfigService.load(self.project_root)
        if config and config.runs:
            raw.update(config.runs)

        local = _load_raw_yaml(self._local_path())
        if local:
            raw.update(local)

        self._raw_cache = raw
        return raw

    def _resolve(self, name: str, raw: dict[str, dict[str, Any]]) -> RunProfile:
        """Resolve a profile's `extends` chain into a validated RunProfile."""
        chain: list[str] = []
        seen: set[str] = set()
        current = name

        while True:
            if current not in raw:
                if current == name:
                    raise ProfileNotFoundError(f"Profile '{name}' not found")
                raise ConfigError(
                    f"Profile '{name}' extends unknown profile '{current}'"
                )
            if current in seen:
                raise ConfigError(
                    f"Profile '{name}' has a cycle in 'extends' (via '{current}')"
                )
            seen.add(current)
            chain.append(current)

            parent = raw[current].get("extends")
            if not parent:
                break
            current = parent

        merged: dict[str, Any] = {}
        for profile_name in reversed(chain):
            merged.update(
                {k: v for k, v in raw[profile_name].items() if k != "extends"}
            )

        return RunProfile.model_validate(merged)

    def save_profile(self, name: str, profile: RunProfile) -> None:
        """Save or update a run profile in slipp.yaml."""
        profile_data = profile.model_dump(
            by_alias=True, exclude_none=True, exclude_defaults=True
        )

        LocalConfigService.create_or_update_with(
            lambda: LocalConfig(name=self.project_root.name, runs={name: profile_data}),
            lambda c: {"runs": {**c.runs, name: profile_data}},
            self.project_root,
        )
        self._raw_cache = None

    def get_profile(self, name: str) -> RunProfile:
        """Return a resolved run profile by name.

        Raises:
            ProfileNotFoundError: If the profile does not exist.
            ConfigError: If the profile's `extends` chain is broken.
        """
        return self._resolve(name, self._raw_profiles())

    def list_profiles(self) -> dict[str, RunProfile]:
        """Return all resolved run profiles, skipping invalid ones."""
        raw = self._raw_profiles()
        resolved: dict[str, RunProfile] = {}
        for name in raw:
            try:
                resolved[name] = self._resolve(name, raw)
            except (ConfigError, ValidationError) as e:
                output.warning(f"Skipping profile '{name}': {e}")
        return resolved

    def delete_profile(self, name: str) -> None:
        """Delete a run profile from slipp.yaml.

        Raises:
            ProfileNotFoundError: If the profile isn't in slipp.yaml (it may
                still exist in a local override file).
        """
        config = LocalConfigService.load(self.project_root)
        if not config or name not in config.runs:
            if name in _load_raw_yaml(self._local_path()):
                raise ProfileNotFoundError(
                    f"Profile '{name}' is defined in {LOCAL_RUNS_FILENAME} — "
                    "edit that file directly to remove it"
                )
            raise ProfileNotFoundError(f"Profile '{name}' not found")

        def mutate(c: LocalConfig) -> dict[str, Any]:
            if name not in c.runs:
                raise ProfileNotFoundError(f"Profile '{name}' not found")
            return {"runs": {k: v for k, v in c.runs.items() if k != name}}

        LocalConfigService.update_with(mutate, self.project_root)
        self._raw_cache = None

    def profile_exists(self, name: str) -> bool:
        """Check whether a profile exists in any layer."""
        return name in self._raw_profiles()


def hash_tunnel_auth(spec: str) -> str:
    """Parse a user:pass spec and bcrypt-hash the password.

    Args:
        spec: Auth spec in user:pass format.

    Returns:
        "user:<bcrypt-hash>" - safe to persist in a git-tracked slipp.yaml.

    Raises:
        ConfigError: If spec is malformed.
    """
    if ":" not in spec:
        raise ConfigError(
            f"Invalid --tunnel-auth format: '{spec}' (expected user:pass)"
        )
    user, password = spec.split(":", 1)
    if not user or not password:
        raise ConfigError(
            "Invalid --tunnel-auth format: user and password cannot be empty"
        )
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return f"{user}:{hashed}"


def _validate_tunnel_specs(tunnel_out: list[str], tunnel_in: list[str]) -> None:
    """Eagerly validate tunnel spec formats so a bad value fails at save time.

    Mirrors the parsing done at execution time (services/run/executor.py)
    without resolving hosts, matching the eager validation already done for
    --tunnel-auth and --proxy -- otherwise a malformed --tunnel-out/-in gets
    persisted into slipp.yaml and only errors on the next `slipp run`.

    Raises:
        TunnelError: If any spec is malformed.
    """
    for spec in tunnel_out:
        parse_tunnel_out(spec)
    for spec in tunnel_in:
        if parse_container_tunnel_in(spec) is None:
            parse_tunnel_in(spec)


def parse_proxy_routes(specs: list[str]) -> list[ProxyRoute]:
    """Parse --proxy specs (format: 'from@host -> to') into ProxyRoute models."""
    routes = []
    for spec in specs:
        if " -> " not in spec:
            raise ProxyRouteError(
                f"Invalid proxy spec: {spec}\nExpected: from@host -> to"
            )

        from_part, to_url = spec.split(" -> ", 1)

        if "@" not in from_part:
            raise ProxyRouteError(
                f"Missing @host in proxy spec: {spec}\nExpected: from@host -> to"
            )

        from_url, host = from_part.rsplit("@", 1)
        routes.append(
            ProxyRoute(
                **{"from": from_url.strip(), "to": to_url.strip(), "host": host.strip()}
            )
        )
    return routes


def _require_tunnel_out_for_auth(
    tunnel_auth: str | None,
    tunnel_out: list[str],
    *,
    existing_out: list[str] | None = None,
) -> None:
    """Raise if --tunnel-auth is set without a tunnel-out.

    Auth applies to Caddy routes (tunnel-out), not tunnel-in.
    """
    if not tunnel_auth or tunnel_out or existing_out:
        return
    if existing_out is None:
        raise ConfigError("--tunnel-auth requires --tunnel-out")
    raise ConfigError(
        "--tunnel-auth requires a tunnel-out (existing or via --tunnel-out)"
    )


def build_profile(
    cmd: str,
    env: list[str],
    vaults: list[str],
    tunnel_out: list[str],
    tunnel_in: list[str],
    proxy: list[str],
    tunnel_auth: str | None = None,
) -> RunProfile:
    """Build a RunProfile from command options."""
    _require_tunnel_out_for_auth(tunnel_auth, tunnel_out)
    _validate_tunnel_specs(tunnel_out, tunnel_in)

    tunnels = None
    if tunnel_out or tunnel_in:
        auth = hash_tunnel_auth(tunnel_auth) if tunnel_auth else None
        tunnels = TunnelConfig.model_validate(
            {"out": tunnel_out, "in": tunnel_in, "auth": auth}
        )

    proxy_routes = parse_proxy_routes(proxy)

    return RunProfile(
        cmd=cmd, env=env, vaults=vaults, tunnels=tunnels, proxy=proxy_routes
    )


def append_extra_args(profile: RunProfile, extra_args: list[str]) -> RunProfile:
    """Append shell-quoted trailing CLI args to the profile's command."""
    if not extra_args:
        return profile
    quoted_args = [shlex.quote(arg) for arg in extra_args]
    extended_cmd = f"{profile.cmd} {' '.join(quoted_args)}"
    return profile.model_copy(update={"cmd": extended_cmd})


def merge_runtime_options(
    profile: RunProfile,
    env: list[str],
    vault: list[str],
    tunnel_out: list[str],
    tunnel_in: list[str],
    proxy: list[str],
    tunnel_auth: str | None = None,
) -> RunProfile:
    """Merge runtime options with saved profile (not persisted).

    Runtime options are added to saved values, not replacing them:
    - env: Appended (CLI values override profile values for same key at execution)
    - vault: Added if not already present
    - tunnels: Added to existing tunnels
    - proxy: Added to existing proxy routes
    - tunnel_auth: Replaces existing auth (requires an existing or new tunnel-out)
    """
    if not any([env, vault, tunnel_out, tunnel_in, proxy, tunnel_auth]):
        return profile

    _validate_tunnel_specs(tunnel_out, tunnel_in)

    merged_env = list(profile.env) + list(env)
    merged_vaults = list(profile.vaults) + [v for v in vault if v not in profile.vaults]

    merged_tunnels = profile.tunnels
    if tunnel_out or tunnel_in or tunnel_auth:
        existing_out = merged_tunnels.out if merged_tunnels else []
        existing_in = merged_tunnels.in_ if merged_tunnels else []
        existing_auth = merged_tunnels.auth if merged_tunnels else None

        _require_tunnel_out_for_auth(tunnel_auth, tunnel_out, existing_out=existing_out)

        merged_tunnels = TunnelConfig.model_validate(
            {
                "out": list(existing_out)
                + [t for t in tunnel_out if t not in existing_out],
                "in": list(existing_in)
                + [t for t in tunnel_in if t not in existing_in],
                "auth": hash_tunnel_auth(tunnel_auth) if tunnel_auth else existing_auth,
            }
        )

    new_proxy = parse_proxy_routes(proxy)
    merged_proxy = list(profile.proxy) + [
        r
        for r in new_proxy
        if not any(
            e.from_ == r.from_ and e.to == r.to and e.host == r.host
            for e in profile.proxy
        )
    ]

    return RunProfile(
        cmd=profile.cmd,
        env=merged_env,
        vaults=merged_vaults,
        tunnels=merged_tunnels,
        proxy=merged_proxy,
    )
