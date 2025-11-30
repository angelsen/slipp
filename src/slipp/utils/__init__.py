"""Shared utilities and exception definitions for slipp.

This package provides common error classes and helper utilities
used throughout the slipp CLI tool.
"""

from .errors import (
    SlippError,
    ConfigError,
    DeploymentError,
    ServiceNotFoundError,
    SSHAuthenticationError,
    SSHConnectionError,
)

__all__ = [
    "SlippError",
    "ConfigError",
    "DeploymentError",
    "ServiceNotFoundError",
    "SSHAuthenticationError",
    "SSHConnectionError",
]
