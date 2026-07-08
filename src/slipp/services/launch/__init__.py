"""Launch pipeline orchestration.

Assembles ordered stage lists for the three launch modes (full,
dockerfile-only, scaffold) and runs each stage in sequence. Stage failures
raise LaunchError.
"""

from collections.abc import Sequence
from typing import Protocol, TypeVar

from slipp.generator import TemplateGenerator
from slipp.services.launch.context import (
    DockerfileContext,
    FullContext,
    ScaffoldContext,
)
from slipp.services.launch.stages import (
    AppRolesStage,
    CaddyConfigStage,
    CaddyRoleStage,
    ComposeGenerationStage,
    DockerfileGenerationStage,
    GroupVarsStage,
    InventoryFileStage,
    InventoryLoadStage,
    InventoryValidationStage,
    PlaybookGenerationStage,
    ProjectScanStage,
    RegistrationStage,
    RequirementsFileStage,
    ScaffoldInventoryStage,
    ScaffoldPromptStage,
    ScaffoldRegistrationStage,
    ScaffoldSummaryStage,
    ScaffoldValidationStage,
    SummaryStage,
    ValidationStage,
)

C_contra = TypeVar("C_contra", contravariant=True)


class PipelineStage(Protocol[C_contra]):
    """Protocol for pipeline stages."""

    def execute(self, context: C_contra) -> None:
        """Execute stage, modifying context in place."""
        ...


def run_full_pipeline(context: FullContext) -> None:
    """Scan the codebase and generate a complete Ansible project."""
    stages: Sequence[PipelineStage[FullContext]] = [
        ValidationStage(),
        ProjectScanStage(),
        InventoryLoadStage(),
        InventoryValidationStage(),
        DockerfileGenerationStage(TemplateGenerator()),
        CaddyConfigStage(),
        InventoryFileStage(),
        PlaybookGenerationStage(),
        GroupVarsStage(),
        CaddyRoleStage(),
        AppRolesStage(),
        RequirementsFileStage(),
        ComposeGenerationStage(),
        RegistrationStage(),
        SummaryStage(),
    ]
    for stage in stages:
        stage.execute(context)


def run_dockerfile_pipeline(context: DockerfileContext) -> None:
    """Scan the codebase and generate Dockerfiles only."""
    stages: Sequence[PipelineStage[DockerfileContext]] = [
        ValidationStage(),
        ProjectScanStage(),
        DockerfileGenerationStage(TemplateGenerator()),
    ]
    for stage in stages:
        stage.execute(context)


def run_scaffold_pipeline(context: ScaffoldContext) -> None:
    """Create Ansible inventory for an existing project."""
    stages: Sequence[PipelineStage[ScaffoldContext]] = [
        ScaffoldValidationStage(),
        ScaffoldPromptStage(),
        ScaffoldInventoryStage(),
        ScaffoldRegistrationStage(),
        ScaffoldSummaryStage(),
    ]
    for stage in stages:
        stage.execute(context)


__all__ = [
    "DockerfileContext",
    "FullContext",
    "ScaffoldContext",
    "run_dockerfile_pipeline",
    "run_full_pipeline",
    "run_scaffold_pipeline",
]
