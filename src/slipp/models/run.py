"""Run profile models for dev environment orchestration.

This module provides Pydantic models for run profiles stored in
slipp.yaml under run_profiles.
"""

from pydantic import BaseModel, Field


class TunnelConfig(BaseModel):
    """SSH tunnel configuration.

    Attributes:
        out: Reverse tunnels (expose local to remote) - format: local_port:domain@host
        in_: Forward tunnels (pull remote to local) - format: service:port@host
    """

    out: list[str] = Field(default_factory=list)
    in_: list[str] = Field(default_factory=list, alias="in")

    model_config = {"populate_by_name": True}


class RunProfile(BaseModel):
    """Single run profile configuration.

    Attributes:
        cmd: Command to execute
        vaults: List of vault project names to inject as env vars
        env: Environment variables as KEY=VALUE strings
        tunnels: SSH tunnel configuration
        acme_email: Email for Let's Encrypt certificate registration
    """

    cmd: str = Field(..., description="Command to execute")
    vaults: list[str] = Field(default_factory=list)
    env: list[str] = Field(
        default_factory=list, description="Environment variables (KEY=VALUE)"
    )
    tunnels: TunnelConfig | None = None
    acme_email: str | None = Field(
        default=None, description="Email for ACME/Let's Encrypt"
    )
