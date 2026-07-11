"""Provider config IO -- ~/.config/slipp/providers.yaml.

Mirrors RegistryIO's load/save/corruption-recovery pattern, but stores
YAML (matching slipp.yaml conventions) since this file is meant to be
occasionally hand-edited, unlike the JSON registry.
"""

import logging
import os
import shutil
from pathlib import Path

import yaml

from slipp.models.provider import (
    GigahostConfig,
    PangolinConfig,
    ProvidersConfig,
    WgDeployConfig,
)
from slipp.utils.files import atomic_write_text

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "providers.yaml"


class ProviderConfigService:
    """Handles loading and saving ~/.config/slipp/providers.yaml.

    Responsibilities:
    - Config file path resolution (XDG spec)
    - Atomic file writes with 0o600 permissions (contains API keys)
    - YAML serialization/deserialization
    - Corruption recovery (backup)
    """

    @staticmethod
    def _get_config_path() -> Path:
        """Get provider config file path following XDG spec."""
        xdg_config = os.getenv("XDG_CONFIG_HOME")
        if xdg_config:
            config_dir = Path(xdg_config) / "slipp"
        else:
            config_dir = Path.home() / ".config" / "slipp"

        config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        return config_dir / CONFIG_FILENAME

    @staticmethod
    def load() -> ProvidersConfig:
        """Load provider config from disk.

        Returns:
            ProvidersConfig (empty if file doesn't exist or is corrupted)
        """
        config_file = ProviderConfigService._get_config_path()

        if not config_file.exists():
            return ProvidersConfig()

        try:
            data = yaml.safe_load(config_file.read_text()) or {}
            return ProvidersConfig(**data)
        except yaml.YAMLError as e:
            backup_path = config_file.with_suffix(".yaml.backup")
            shutil.copy(config_file, backup_path)
            logger.warning(
                f"Provider config corrupted: {e}. Backed up to: {backup_path}"
            )
            return ProvidersConfig()
        except Exception as e:
            logger.warning(f"Failed to load provider config: {e}")
            return ProvidersConfig()

    @staticmethod
    def save(config: ProvidersConfig) -> None:
        """Save provider config with atomic write, 0o600 permissions."""
        config_file = ProviderConfigService._get_config_path()
        data = config.model_dump(exclude_none=True, mode="json")
        content = yaml.dump(data, default_flow_style=False, sort_keys=False)
        atomic_write_text(config_file, content, mode=0o600)

    @staticmethod
    def get_gigahost() -> GigahostConfig | None:
        """Get Gigahost config, with GIGAHOST_API_KEY env var taking precedence.

        The env var override lets CI/automation supply a key without ever
        writing providers.yaml.
        """
        env_key = os.getenv("GIGAHOST_API_KEY")
        if env_key:
            cached = ProviderConfigService.load().gigahost
            return GigahostConfig(
                api_key=env_key,
                account_name=cached.account_name if cached else None,
                account_id=cached.account_id if cached else None,
            )

        return ProviderConfigService.load().gigahost

    @staticmethod
    def set_gigahost(gigahost: GigahostConfig) -> None:
        """Save (or replace) the Gigahost config."""
        config = ProviderConfigService.load()
        config.gigahost = gigahost
        ProviderConfigService.save(config)

    @staticmethod
    def remove_gigahost() -> None:
        """Remove the Gigahost config, if any."""
        config = ProviderConfigService.load()
        config.gigahost = None
        ProviderConfigService.save(config)

    @staticmethod
    def get_pangolin() -> PangolinConfig | None:
        """Get Pangolin config, with PANGOLIN_SESSION_COOKIE env var taking precedence.

        The env var override lets CI/automation supply a cookie without ever
        writing providers.yaml.
        """
        env_cookie = os.getenv("PANGOLIN_SESSION_COOKIE")
        if env_cookie:
            cached = ProviderConfigService.load().pangolin
            if cached:
                return cached.model_copy(update={"session_cookie": env_cookie})
            return PangolinConfig(session_cookie=env_cookie)

        return ProviderConfigService.load().pangolin

    @staticmethod
    def set_pangolin(pangolin: PangolinConfig) -> None:
        """Save (or replace) the Pangolin config."""
        config = ProviderConfigService.load()
        config.pangolin = pangolin
        ProviderConfigService.save(config)

    @staticmethod
    def remove_pangolin() -> None:
        """Remove the Pangolin config, if any."""
        config = ProviderConfigService.load()
        config.pangolin = None
        ProviderConfigService.save(config)

    @staticmethod
    def get_wg_deploy() -> WgDeployConfig | None:
        """Get wg-deploy config."""
        return ProviderConfigService.load().wg_deploy

    @staticmethod
    def set_wg_deploy(wg_deploy: WgDeployConfig) -> None:
        """Save (or replace) the wg-deploy config."""
        config = ProviderConfigService.load()
        config.wg_deploy = wg_deploy
        ProviderConfigService.save(config)

    @staticmethod
    def remove_wg_deploy() -> None:
        """Remove the wg-deploy config, if any."""
        config = ProviderConfigService.load()
        config.wg_deploy = None
        ProviderConfigService.save(config)
