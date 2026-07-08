"""Pipeline infrastructure for launch command execution."""

from collections.abc import Sequence
from typing import Generic, Protocol, TypeVar

C_contra = TypeVar("C_contra", contravariant=True)


class PipelineStage(Protocol[C_contra]):
    """Protocol for pipeline stages."""

    def execute(self, context: C_contra) -> None:
        """Execute stage, modifying context in place."""
        ...


C = TypeVar("C")


class LaunchPipeline(Generic[C]):
    """Orchestrates launch command execution through a series of stages."""

    def __init__(self, stages: Sequence["PipelineStage[C]"]):
        self.stages = stages

    def execute(self, context: C) -> C:
        """Execute all stages in order."""
        for stage in self.stages:
            stage.execute(context)
        return context
