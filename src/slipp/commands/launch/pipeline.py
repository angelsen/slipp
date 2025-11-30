"""Pipeline infrastructure for launch command execution."""

from typing import Any, Protocol


class PipelineStage(Protocol):
    """Protocol for pipeline stages."""

    def execute(self, context: Any) -> None:
        """Execute stage, modifying context in place."""
        ...


class LaunchPipeline:
    """Orchestrates launch command execution through a series of stages."""

    def __init__(self, stages: list[PipelineStage]):
        self.stages = stages

    def execute(self, context: Any) -> Any:
        """Execute all stages in order."""
        for stage in self.stages:
            stage.execute(context)
        return context
