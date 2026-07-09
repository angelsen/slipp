"""Provision state model for resume-able VPS provisioning."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ProvisionPhase(StrEnum):
    ORDERED = "ordered"
    PROVISIONED = "provisioned"
    INSTALLING = "installing"


class ProvisionState(BaseModel):
    """Persisted state for an in-progress VPS provision.

    Saved to ~/.config/slipp/provisions/<name>.yaml after the VPS order
    is placed, updated as the flow progresses, deleted on completion.
    """

    name: str = Field(..., min_length=1)
    order_ids: list[int] | None = None
    srv_id: int | None = None
    ip: str | None = None
    phase: ProvisionPhase = ProvisionPhase.ORDERED
    provider: str = "gigahost"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
