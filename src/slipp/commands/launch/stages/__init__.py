"""Launch pipeline stages."""

from .ansible import AppRolesStage, GroupVarsStage, PlaybookGenerationStage
from .caddy import CaddyConfigStage, CaddyRoleStage
from .common import FileGenerationStage, ValidationStage
from .compose import ComposeGenerationStage
from .dockerfile import DockerfileGenerationStage
from .inventory import InventoryFileStage, InventoryLoadStage, InventoryValidationStage
from .registry import RegistrationStage, SummaryStage
from .scaffold import (
    ScaffoldInventoryStage,
    ScaffoldPromptStage,
    ScaffoldRegistrationStage,
    ScaffoldSummaryStage,
    ScaffoldValidationStage,
)
from .scan import ProjectScanStage

__all__ = [
    "FileGenerationStage",
    "ValidationStage",
    "ProjectScanStage",
    "InventoryLoadStage",
    "InventoryValidationStage",
    "InventoryFileStage",
    "DockerfileGenerationStage",
    "CaddyConfigStage",
    "CaddyRoleStage",
    "PlaybookGenerationStage",
    "GroupVarsStage",
    "AppRolesStage",
    "ComposeGenerationStage",
    "RegistrationStage",
    "SummaryStage",
    "ScaffoldValidationStage",
    "ScaffoldPromptStage",
    "ScaffoldInventoryStage",
    "ScaffoldRegistrationStage",
    "ScaffoldSummaryStage",
]
