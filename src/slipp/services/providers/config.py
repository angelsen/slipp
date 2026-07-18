"""Provider config IO -- ~/.config/slipp/providers.yaml.

Stores YAML (matching slipp.yaml conventions) since this file is meant to
be occasionally hand-edited, unlike the JSON registry. The load/save/
corruption-recovery mechanics live in utils/config_store.py.
"""

import os
from pathlib import Path

from slipp.models.provider import (
    GigahostConfig,
    PangolinConfig,
    ProvidersConfig,
    WgDeployConfig,
)
from slipp.utils.config_store import (
    config_store_lock,
    load_model,
    save_model,
    slipp_config_dir,
)
from slipp.utils.errors import ConfigError

CONFIG_FILENAME = "providers.yaml"


class ProviderConfigService:
    """Handles loading and saving ~/.config/slipp/providers.yaml."""

    @staticmethod
    def _get_config_path() -> Path:
        """Get provider config file path following XDG spec."""
        return slipp_config_dir() / CONFIG_FILENAME

    @staticmethod
    def load() -> ProvidersConfig:
        """Load provider config from disk (empty if missing or corrupted)."""
        return load_model(
            ProviderConfigService._get_config_path(),
            ProvidersConfig,
            default=ProvidersConfig(),
            label="Provider config",
        )

    @staticmethod
    def save(config: ProvidersConfig) -> None:
        """Save provider config with atomic write, 0o600 permissions."""
        save_model(ProviderConfigService._get_config_path(), config, exclude_none=True)

    @staticmethod
    def _update(
        attr: str, value: GigahostConfig | PangolinConfig | WgDeployConfig | None
    ) -> None:
        with config_store_lock(ProviderConfigService._get_config_path()):
            config = ProviderConfigService.load()
            setattr(config, attr, value)
            ProviderConfigService.save(config)

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
            )

        return ProviderConfigService.load().gigahost

    @staticmethod
    def set_gigahost(gigahost: GigahostConfig) -> None:
        """Save (or replace) the Gigahost config."""
        ProviderConfigService._update("gigahost", gigahost)

    @staticmethod
    def remove_gigahost() -> None:
        """Remove the Gigahost config, if any."""
        ProviderConfigService._update("gigahost", None)

    @staticmethod
    def get_pangolin() -> PangolinConfig | None:
        """Get Pangolin config, with PANGOLIN_SESSION_COOKIE env var
        taking precedence over the cached secret only.

        org/base_url always come from providers.yaml -- matches
        wg_deploy.repo_path having no env override at all: identity/
        location config isn't meant to be env-overridable, only secrets
        are (same reasoning as GIGAHOST_API_KEY). Run 'slipp providers
        add pangolin' once, even in CI, before relying on the env var to
        rotate just the cookie.

        Raises:
            ConfigError: PANGOLIN_SESSION_COOKIE is set but no cached
                config exists to source org/base_url from.
        """
        cached = ProviderConfigService.load().pangolin
        env_cookie = os.getenv("PANGOLIN_SESSION_COOKIE")

        if not env_cookie:
            return cached
        if not cached:
            raise ConfigError(
                "PANGOLIN_SESSION_COOKIE is set but org/base_url aren't "
                "configured -- run 'slipp providers add pangolin' once"
            )
        return cached.model_copy(update={"session_cookie": env_cookie})

    @staticmethod
    def set_pangolin(pangolin: PangolinConfig) -> None:
        """Save (or replace) the Pangolin config."""
        ProviderConfigService._update("pangolin", pangolin)

    @staticmethod
    def remove_pangolin() -> None:
        """Remove the Pangolin config, if any."""
        ProviderConfigService._update("pangolin", None)

    @staticmethod
    def get_wg_deploy() -> WgDeployConfig | None:
        """Get wg-deploy config."""
        return ProviderConfigService.load().wg_deploy

    @staticmethod
    def set_wg_deploy(wg_deploy: WgDeployConfig) -> None:
        """Save (or replace) the wg-deploy config."""
        ProviderConfigService._update("wg_deploy", wg_deploy)

    @staticmethod
    def remove_wg_deploy() -> None:
        """Remove the wg-deploy config, if any."""
        ProviderConfigService._update("wg_deploy", None)
