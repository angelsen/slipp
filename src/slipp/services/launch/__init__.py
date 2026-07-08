"""Launch pipeline orchestration.

Assembles pipeline stages for the three launch modes (full, dockerfile-only,
scaffold) and runs them via LaunchPipeline. Stage failures raise LaunchError.
"""

from slipp.generator import TemplateGenerator
from slipp.services.launch.context import (
    BaseContext,
    DockerfileContext,
    FullContext,
    ScaffoldContext,
)
from slipp.services.launch.pipeline import LaunchPipeline, PipelineStage
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


def run_full_pipeline(context: FullContext) -> None:
    """Scan the codebase and generate a complete Ansible project."""
    stages: list[PipelineStage[FullContext]] = [
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
    LaunchPipeline(stages).execute(context)


def run_dockerfile_pipeline(context: DockerfileContext) -> None:
    """Scan the codebase and generate Dockerfiles only."""
    stages: list[PipelineStage[DockerfileContext]] = [
        ValidationStage(),
        ProjectScanStage(),
        DockerfileGenerationStage(TemplateGenerator()),
    ]
    LaunchPipeline(stages).execute(context)


def run_scaffold_pipeline(context: ScaffoldContext) -> None:
    """Create Ansible inventory for an existing project."""
    stages: list[PipelineStage[ScaffoldContext]] = [
        ScaffoldValidationStage(),
        ScaffoldPromptStage(),
        ScaffoldInventoryStage(),
        ScaffoldRegistrationStage(),
        ScaffoldSummaryStage(),
    ]
    LaunchPipeline(stages).execute(context)


__all__ = [
    "BaseContext",
    "DockerfileContext",
    "FullContext",
    "ScaffoldContext",
    "run_dockerfile_pipeline",
    "run_full_pipeline",
    "run_scaffold_pipeline",
]
