"""VPS bootstrap provisioning services."""

from slipp.services.bootstrap.account import provision_account
from slipp.services.bootstrap.registry import bootstrap_registry_auth

__all__ = ["bootstrap_registry_auth", "provision_account"]
